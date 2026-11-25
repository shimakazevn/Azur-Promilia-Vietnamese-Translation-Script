# -*- coding: utf-8 -*-
"""CRC32 配平：在不改变文件长度的前提下，把整包 CRC 配回指定值。

原理：CRC32 是 GF(2) 上的线性变换。
  处理字节 b：state -> T(state) ^ table[b]，table[0]=0
  4 字节的自由位对最终 CRC 的贡献是 32x32 线性映射 M，
  且 M 只依赖「这 4 字节之后还有多少字节」以及「起始状态」，
  与文件内容和被改位置之前的字节无关 -> 可以纯矩阵算，不用扫大文件。

求解 M x = target ^ base，x 就是那 4 个字节。
"""
import zlib, struct

POLY = 0xEDB88320
TABLE = []
for i in range(256):
    c = i
    for _ in range(8):
        c = (c >> 1) ^ (POLY if c & 1 else 0)
    TABLE.append(c)


def _advance_byte(state, b):
    return (state >> 8) ^ TABLE[(state ^ b) & 0xFF]


class GF2Mat:
    """32x32 的 GF(2) 矩阵，按列存（第 i 列是 e_i 的像）。"""
    def __init__(self, cols=None):
        self.cols = cols if cols is not None else [1 << i for i in range(32)]

    def apply(self, v):
        r = 0
        for i in range(32):
            if (v >> i) & 1:
                r ^= self.cols[i]
        return r

    def mul(self, other):
        return GF2Mat([self.apply(c) for c in other.cols])

    def power(self, n):
        r = GF2Mat()
        b = self
        while n:
            if n & 1:
                r = r.mul(b)
            b = b.mul(b)
            n >>= 1
        return r


# T：推进一个字节（对状态的作用），即 state -> (state>>8) ^ TABLE[state & 0xFF]
T = GF2Mat([_advance_byte(1 << i, 0) for i in range(32)])


def solve_linear(mat_cols, rhs):
    """解 M x = rhs，mat_cols 为 32 列。返回 x 或 None（无解）。"""
    # 增广：把每一列当作一个方程的系数不太好；改成行视角。
    # 构造 32x32 的行矩阵 A，A[row][col]
    A = [[(mat_cols[c] >> r) & 1 for c in range(32)] for r in range(32)]
    b = [(rhs >> r) & 1 for r in range(32)]
    # 高斯消元
    where = [-1] * 32
    row = 0
    for col in range(32):
        piv = -1
        for r in range(row, 32):
            if A[r][col]:
                piv = r
                break
        if piv < 0:
            continue
        A[row], A[piv] = A[piv], A[row]
        b[row], b[piv] = b[piv], b[row]
        for r in range(32):
            if r != row and A[r][col]:
                for c in range(32):
                    A[r][c] ^= A[row][c]
                b[r] ^= b[row]
        where[col] = row
        row += 1
    x = 0
    for col in range(32):
        if where[col] >= 0 and b[where[col]]:
            x |= 1 << col
    # 校验
    if mat_cols_applied(mat_cols, x) != rhs:
        return None
    return x


def mat_cols_applied(cols, v):
    r = 0
    for i in range(32):
        if (v >> i) & 1:
            r ^= cols[i]
    return r


def patch_crc(data, target_crc, pos):
    """把 data[pos:pos+4] 设为某值，使 crc32(data) == target_crc。

    data 必须是 bytearray（就地修改）。长度不变。
    """
    n = len(data)
    assert 0 <= pos <= n - 4
    tail_len = n - pos - 4
    Ttail = T.power(tail_len)

    # 4 字节中第 j 个字节、第 k 位对状态的贡献（处理完后）
    base_cols = []
    for i in range(32):
        j = i // 8
        k = i % 8
        # tbl[1<<k] 在位置 j，经过 4 字节处理后的剩余推进次数 = 3-j
        c = TABLE[1 << k]
        c = T.power(3 - j).apply(c)
        base_cols.append(c)
    cols = [Ttail.apply(c) for c in base_cols]

    saved = bytes(data[pos:pos + 4])
    data[pos:pos + 4] = b"\x00\x00\x00\x00"
    z = zlib.crc32(bytes(data)) & 0xFFFFFFFF
    data[pos:pos + 4] = saved

    rhs = (target_crc ^ z) & 0xFFFFFFFF
    x = solve_linear(cols, rhs)
    if x is None:
        return False
    data[pos:pos + 4] = struct.pack("<I", x)
    return (zlib.crc32(bytes(data)) & 0xFFFFFFFF) == (target_crc & 0xFFFFFFFF)


if __name__ == "__main__":
    import os, time
    # 自测：造一个文件，改几个字节，再配平
    d = bytearray(os.urandom(100000) + b"AZURPROMILIA" * 1000)
    orig_crc = zlib.crc32(bytes(d)) & 0xFFFFFFFF
    d[1000:1010] = b"0123456789"
    print("改内容后 crc:", hex(zlib.crc32(bytes(d)) & 0xFFFFFFFF), "目标:", hex(orig_crc))
    t0 = time.time()
    ok = patch_crc(d, orig_crc, len(d) - 4)
    print("配平:", ok, "耗时 %.3fs" % (time.time() - t0))
    print("配平后 crc:", hex(zlib.crc32(bytes(d)) & 0xFFFFFFFF), "长度:", len(d))
    # 再测中间位置
    d2 = bytearray(os.urandom(50000))
    c2 = zlib.crc32(bytes(d2)) & 0xFFFFFFFF
    d2[100:110] = b"abcdefghij"
    print("中间配平:", patch_crc(d2, c2, 25000), hex(zlib.crc32(bytes(d2)) & 0xFFFFFFFF) == hex(c2))
