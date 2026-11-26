# -*- coding: utf-8 -*-
# CRC32 配平：在不改变文件长度的前提下，把整段 CRC 配回指定值。
# 来源：改编自 xiayuan0817/Azur-Promilia-Chinese-Translation-Script（Apache-2.0）。
"""原理：CRC32 是 GF(2) 上的线性变换。
处理字节 b：state -> T(state) ^ table[b]，table[0]=0。
4 字节自由位对最终 CRC 的贡献是 32x32 线性映射 M，M 只依赖「这 4 字节之后还有多少字节」，
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


T = GF2Mat([_advance_byte(1 << i, 0) for i in range(32)])
BASE_COLS = tuple(
    T.power(3 - (i // 8)).apply(TABLE[1 << (i % 8)])
    for i in range(32)
)


def crc32_raw(data):
    return (zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF) & 0xFFFFFFFF


def solve_linear(mat_cols, rhs):
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

    # 校验
    chk = 0
    for col in range(32):
        if (x >> col) & 1:
            chk ^= mat_cols[col]
    if chk != (rhs & 0xFFFFFFFF):
        return None
    return x


def patch_crc(data, target_crc, pos, current_crc=None):
    """把 data[pos:pos+4] 设为某值，使 crc32(data) == target_crc（就地修改，长度不变）。"""
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
