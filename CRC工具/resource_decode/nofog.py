# -*- coding: utf-8 -*-
"""蓝色星原（日服 AZUPRO_JP）反虚化工具主脚本。

把 .r 资源包里控制虚化的 MonoBehaviour 参数归零 / 设 -360，并保持
文件大小与 CRC32 与官方原包完全一致（等长 + CRC 配平），让游戏自检通过。

用法:
  1. 装依赖:  pip install UnityPy pycryptodome lz4
  2. 设密钥:  set AZUR_BUNDLE_KEY=<32位hex>     （密钥需自行获取，本仓库不包含）
  3. 单文件:  python nofog.py <文件.r> <输出目录>
  4. 多文件:  python nofog.py --names a.r,b.r --dir <包目录> <输出目录>
"""
import os
import sys
import struct
import zlib
import warnings
import argparse
from pathlib import Path

import UnityPy
from UnityPy.helpers import ArchiveStorageManager as asm
from UnityPy.streams import EndianBinaryReader

warnings.filterwarnings('ignore')

import lz4.block
from reencrypt_bundle import encrypt_lz4, wrap
from crcpatch import patch_crc

# 虚化参数 → 目标值
FLOAT0 = {'void_distance', 'hide_distance', 'void_npc_distance', 'void_npc_radius', 'voidNpcRadius'}
FLOAT_N360 = {'void_start_angle', 'void_npc_angle', 'void_start_angle_mount'}
FLOAT_N361 = {'void_max_angle', 'void_max_angle_mount'}
INT0 = {'void_coefficient'}
ALLKEYS = FLOAT0 | FLOAT_N360 | FLOAT_N361 | INT0 | {'hidenFx'}


def setup(key_hex):
    """设置解密密钥与签名。签名是蛮啾定制的，不是 UnityPy 默认的 UnityCN。"""
    if not key_hex or len(key_hex) != 32:
        raise SystemExit("请先设置 AZUR_BUNDLE_KEY（32 位 hex）。")
    asm.UNITY3D_SIGNATURE = b'#$manjuuunity*!@'
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f1"
    UnityPy.set_assetbundle_decrypt_key(bytes.fromhex(key_hex))


def walk(data):
    """从 offset 0 起顺序枚举 pack 内的 UnityFS 段 (offset, size)。"""
    segs = []
    p = 0
    n = len(data)
    while p + 32 <= n:
        if data[p:p + 7] != b'UnityFS':
            break
        q = p + 12
        for _ in range(2):
            e = data.index(b'\0', q)
            q = e + 1
        size = struct.unpack_from('>q', data, q)[0]
        if size <= 0 or p + size > n:
            break
        segs.append((p, size))
        p += size
    return segs


def meta(raw):
    r = EndianBinaryReader(raw)
    r.read_string_to_null(); r.read_u_int(); r.read_string_to_null(); r.read_string_to_null()
    hp = r.Position
    size = r.read_long(); cs = r.read_u_int(); us = r.read_u_int(); fl = r.read_u_int(); he = r.Position
    dec = asm.ArchiveStorageDecryptor(r) if fl & 0x400 else None
    ep = r.Position
    r.align_stream(16)
    start = r.Position
    bu = next(iter(UnityPy.load(raw).files.values()))
    ci = raw[size - cs:size] if fl & 128 else raw[start:start + cs]
    info = bu.decompress_data(ci, us, fl)
    count = struct.unpack_from('>I', info, 16)[0]
    p = start if fl & 128 else start + cs
    if fl & 512:
        p = (p + 15) // 16 * 16
    chunks = []
    for i in range(count):
        u, c, f = struct.unpack_from('>IIH', info, 20 + 10 * i)
        d = bu.decompress_data(raw[p:p + c], u, f, i)
        assert len(d) == u
        p += c
        chunks.append(d)
    return hp, he, ep, dec, info, b''.join(chunks)


def repack(raw, original, slot, blocksize=131072):
    """把 raw 重新压缩+加密，塞进 slot 大小的槽位，并把 CRC32 配平为 original 的 CRC。"""
    hp, he, ep, dec, info, plain = meta(raw)
    _, ohe, oep, odec, _, _ = meta(original)
    assert raw[he:ep] == original[ohe:oep], "加密头不一致"
    compressed = []
    entries = []
    for i, p in enumerate(range(0, len(plain), blocksize)):
        chunk = plain[p:p + blocksize]
        c = lz4.block.compress(chunk, mode='high_compression', compression=12, store_size=False)
        if len(c) >= len(chunk):
            c = chunk
            fl = 0
        else:
            c = encrypt_lz4(c, i, odec)
            fl = 0x103
        compressed.append(c)
        entries.append((len(chunk), len(c), fl))
    n = struct.unpack_from('>I', info, 16)[0]
    ni = info[:16] + struct.pack('>I', len(entries)) + b''.join(struct.pack('>IIH', *x) for x in entries) + info[20 + 10 * n:]
    ci = lz4.block.compress(ni, mode='high_compression', compression=12, store_size=False)
    head = bytearray(raw[:he])
    struct.pack_into('>QIII', head, hp, slot, len(ci), len(ni), 0x643)
    out = head + original[ohe:oep]
    freepos = len(out)
    out.extend(bytes((-len(out)) % 16))
    assert len(out) - freepos >= 4
    out += ci
    out.extend(bytes((-len(out)) % 16))
    out += b''.join(compressed)
    actual = len(out)
    if actual > slot:
        return None  # 超槽位
    out.extend(bytes(slot - len(out)))
    assert patch_crc(out, zlib.crc32(original) & 0xffffffff, freepos)
    return bytes(out)


def process_seg(seg, slot):
    """改段内虚化字段并重打包。返回 (是否含虚化, 新段 bytes 或 None)。"""
    env = UnityPy.load(seg)
    hit = False
    for o in env.objects:
        if o.type.name != 'MonoBehaviour':
            continue
        try:
            t = o.read_typetree()
        except Exception:
            continue
        if not isinstance(t, dict):
            continue
        if not any(k in t for k in ALLKEYS):
            continue
        changed = False
        for k in list(t.keys()):
            if k in FLOAT0:
                t[k] = 0.0; changed = True
            elif k in FLOAT_N360:
                t[k] = -360.0; changed = True
            elif k in FLOAT_N361:
                t[k] = -361.0; changed = True
            elif k in INT0:
                t[k] = 0; changed = True
            elif k == 'hidenFx' and t[k]:
                t[k] = []; changed = True
        if changed:
            o.save_typetree(t)
            hit = True
    if not hit:
        return False, None
    plain = next(iter(env.files.values())).save(packer='lz4')
    b, _ = wrap(plain, seg)
    cand = repack(b, seg, slot)
    if cand is None:
        return True, None
    return True, cand


def process_file(src: Path, out_dir: Path):
    data = src.read_bytes()
    segs = walk(data)
    orig_crc = zlib.crc32(data) & 0xffffffff
    out = bytearray(data)
    done = 0
    overflow = 0
    for off, size in segs:
        seg = bytes(data[off:off + size])
        hit, cand = process_seg(seg, size)
        if not hit:
            continue
        if cand is None:
            overflow += 1
            print(f"  段 offset={off} 超槽位，跳过", flush=True)
            continue
        out[off:off + size] = cand
        done += 1
    final = bytes(out)
    ok_size = len(final) == len(data)
    ok_crc = (zlib.crc32(final) & 0xffffffff) == orig_crc
    dst = out_dir / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(final)
    print(f"{src.name}: 段数={len(segs)} 改={done} 超槽={overflow} size_ok={ok_size} crc_ok={ok_crc}")
    return ok_size and ok_crc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*', help='要处理的 .r 文件路径')
    ap.add_argument('out', help='输出目录')
    ap.add_argument('--names', help='逗号分隔的文件名（配合 --dir）')
    ap.add_argument('--dir', help='包所在目录（配合 --names）')
    args = ap.parse_args()

    setup(os.environ.get('AZUR_BUNDLE_KEY', ''))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [Path(f) for f in args.files]
    if args.dir and args.names:
        d = Path(args.dir)
        targets = [d / n.strip() for n in args.names.split(',')]

    if not targets:
        ap.print_help()
        return

    all_ok = True
    for t in targets:
        if not t.exists():
            print(f"文件不存在: {t}")
            all_ok = False
            continue
        all_ok = process_file(t, out_dir) and all_ok

    print("全部完成" if all_ok else "有失败/超槽位，见上方输出")


if __name__ == '__main__':
    main()
