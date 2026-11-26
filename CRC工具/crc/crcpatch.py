# -*- coding: utf-8 -*-
"""CRC32 配平：在不改变文件长度的前提下，把整包 CRC 配回指定值。

原理：CRC32 是 GF(2) 上的线性变换。
  处理字节 b：state -> T(state) ^ table[b]，table[0]=0
  4 字节的自由位对最终 CRC 的贡献是 32x32 线性映射 M，
  且 M 只依赖「这 4 字节之后还有多少字节」以及「起始状态」，
  与文件内容和被改位置之前的字节无关 -> 可以纯矩阵算，不用扫大文件。

求解 M x = target ^ base，x 就是那 4 个字节。
"""
import struct
import zlib

POLY = 0xEDB88320
TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (POLY if _c & 1 else 0)
    TABLE.append(_c)
TABLE = tuple(TABLE)


def _advance_byte(state, b):
    return (state >> 8) ^ TABLE[(state ^ b) & 0xFF]


class GF2Mat:
    """32x32 的 GF(2) 矩阵，按列存（第 i 列是 e_i 的像）。"""

    def __init__(self, cols=None):
        self.cols = tuple(cols) if cols is not None else tuple(1 << i for i in range(32))

    def apply(self, v):
        r = 0
        cols = self.cols
        while v:
            lsb = v & -v
            r ^= cols[lsb.bit_length() - 1]
            v ^= lsb
        return r

    def mul(self, other):
        apply = self.apply
        return GF2Mat([apply(c) for c in other.cols])

    def power(self, n):
        r = GF2Mat()
        b = self
        while n:
            if n & 1:
                r = r.mul(b)
            n >>= 1
            if n:
                b = b.mul(b)
        return r


# T：推进一个字节（对状态的作用），即 state -> (state>>8) ^ TABLE[state & 0xFF]
T = GF2Mat([_advance_byte(1 << i, 0) for i in range(32)])

# 4 字节自由位在位置 j=0..3、位 k=0..7 对紧随其后状态的线性贡献
BASE_COLS = tuple(
    T.power(3 - (i // 8)).apply(TABLE[1 << (i % 8)])
    for i in range(32)
)


def crc32_raw(data):
    """零初始状态、无末尾异或的线性 CRC32（满足 crc32_raw(A^B) == crc32_raw(A) ^ crc32_raw(B)）。"""
    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def crc32_delta(diff_bytes, tail_len):
    """计算局部异或差分 diff_bytes（其后还有 tail_len 字节）对整包 CRC32 的异或贡献。"""
    raw = crc32_raw(diff_bytes)
    if tail_len <= 0:
        return raw
    return T.power(tail_len).apply(raw)


def mat_cols_applied(cols, v):
    r = 0
    while v:
        lsb = v & -v
        r ^= cols[lsb.bit_length() - 1]
        v ^= lsb
    return r


def solve_linear(mat_cols, rhs):
    """解 M x = rhs，mat_cols 为 32 列。返回 x 或 None（无解）。"""
    # 按行打包成 33-bit 整数（低 32 位为系数，第 32 位为 rhs bit），高斯消元一步位异或完成。
    rows = []
    for r in range(32):
        mask = 0
        for c in range(32):
            if (mat_cols[c] >> r) & 1:
                mask |= 1 << c
        if (rhs >> r) & 1:
            mask |= 1 << 32
        rows.append(mask)

    where = [-1] * 32
    row = 0
    for col in range(32):
        bit = 1 << col
        piv = -1
        for r in range(row, 32):
            if rows[r] & bit:
                piv = r
                break
        if piv < 0:
            continue
        rows[row], rows[piv] = rows[piv], rows[row]
        piv_row = rows[row]
        for r in range(32):
            if r != row and (rows[r] & bit):
                rows[r] ^= piv_row
        where[col] = row
        row += 1

    x = 0
    for col in range(32):
        w = where[col]
        if w >= 0 and ((rows[w] >> 32) & 1):
            x |= 1 << col

    if mat_cols_applied(mat_cols, x) != (rhs & 0xFFFFFFFF):
        return None
    return x


def patch_crc(data, target_crc, pos, current_crc=None):
    """把 data[pos:pos+4] 设为某值，使 crc32(data) == target_crc。

    data 必须是 bytearray（就地修改）。长度不变。
    可选传入 current_crc 以跳过全文件扫描。
    """
    n = len(data)
    assert 0 <= pos <= n - 4
    tail_len = n - pos - 4
    Ttail = T.power(tail_len)
    cols = [Ttail.apply(c) for c in BASE_COLS]

    mv = memoryview(data)
    saved_val = struct.unpack_from("<I", mv, pos)[0]
    if current_crc is None:
        mv[pos:pos + 4] = b"\x00\x00\x00\x00"
        z = zlib.crc32(mv) & 0xFFFFFFFF
        mv[pos:pos + 4] = struct.pack("<I", saved_val)
        rhs = (target_crc ^ z) & 0xFFFFFFFF
        x = solve_linear(cols, rhs)
        if x is None:
            return False
        mv[pos:pos + 4] = struct.pack("<I", x)
        return (zlib.crc32(mv) & 0xFFFFFFFF) == (target_crc & 0xFFFFFFFF)

    rhs = (target_crc ^ current_crc) & 0xFFFFFFFF
    delta = solve_linear(cols, rhs)
    if delta is None:
        return False
    struct.pack_into("<I", mv, pos, saved_val ^ delta)
    return True


if __name__ == "__main__":
    import os
    import time

    d = bytearray(os.urandom(100000) + b"AZURPROMILIA" * 1000)
    orig_crc = zlib.crc32(d) & 0xFFFFFFFF
    d[1000:1010] = b"0123456789"
    print("改内容后 crc:", hex(zlib.crc32(d) & 0xFFFFFFFF), "目标:", hex(orig_crc))
    t0 = time.time()
    ok = patch_crc(d, orig_crc, len(d) - 4)
    print("配平:", ok, "耗时 %.3fs" % (time.time() - t0))
    print("配平后 crc:", hex(zlib.crc32(d) & 0xFFFFFFFF), "长度:", len(d))

    d2 = bytearray(os.urandom(50000))
    c2 = zlib.crc32(d2) & 0xFFFFFFFF
    d2[100:110] = b"abcdefghij"
    print("中间配平:", patch_crc(d2, c2, 25000), (zlib.crc32(d2) & 0xFFFFFFFF) == c2)
