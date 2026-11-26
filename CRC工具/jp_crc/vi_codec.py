# -*- coding: utf-8 -*-
"""Self-contained JP UnityFS / MMap / Font / CRC32 codec for Azur Promilia VI localization."""
from pathlib import Path
import io
import struct
import sys
import zlib

from Crypto.Cipher import AES
from fontTools import subset
from fontTools.ttLib import TTFont
import lz4.block
import UnityPy
from UnityPy.helpers import ArchiveStorageManager as asm
from UnityPy.streams import EndianBinaryReader

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "crc"))
from crcpatch import patch_crc  # noqa: E402
import crcchain as C  # noqa: E402

asm.UNITY3D_SIGNATURE = b"#$manjuuunity*!@"
UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.62f3"
UnityPy.set_assetbundle_decrypt_key(b"z4l23bh5#35h&321")

MMAP_KEY = bytes.fromhex("c622794f63860f3c6e18132e2f08892aff235ae89110595c1f1e3092c81cf297")
MMAP_IV = bytes.fromhex("9774562a1898c9f71b4a3a0af29edfeb")


def _mmap_keystream(header_4120: bytes) -> bytes:
    assert len(header_4120) == 4120
    pt = AES.new(MMAP_KEY, AES.MODE_CBC, MMAP_IV).decrypt(header_4120[8:4120])
    pad = pt[-1]
    assert 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad
    ks = pt[:-pad]
    assert len(ks) == 4096
    return ks


def decode_mmap(raw: bytes) -> bytes:
    ks = _mmap_keystream(raw[:4120])
    ks2 = ks + ks
    out = bytearray()
    pos = 4120
    n = len(raw)
    while pos < n:
        page = pos >> 12
        in_page = pos & 0xFFF
        take = min(0x1000 - in_page, n - pos)
        kstart = (ks[page & 0xFF] + in_page) & 0xFFF
        x = int.from_bytes(raw[pos : pos + take], "little") ^ int.from_bytes(
            ks2[kstart : kstart + take], "little"
        )
        out += x.to_bytes(take, "little")
        pos += take
    return bytes(out)


def encode_mmap(plain: bytes, original: bytes) -> bytes:
    ks = _mmap_keystream(original[:4120])
    ks2 = ks + ks
    out = bytearray(original[:4120])
    pos = 4120
    p_off = 0
    n_plain = len(plain)
    while p_off < n_plain:
        page = pos >> 12
        in_page = pos & 0xFFF
        take = min(0x1000 - in_page, n_plain - p_off)
        kstart = (ks[page & 0xFF] + in_page) & 0xFFF
        x = int.from_bytes(plain[p_off : p_off + take], "little") ^ int.from_bytes(
            ks2[kstart : kstart + take], "little"
        )
        out += x.to_bytes(take, "little")
        pos += take
        p_off += take
    return bytes(out)


def encrypt_lz4(data: bytes, index: int, dec_obj) -> bytes:
    inv_idx = [0] * 16
    for pos, val in enumerate(dec_obj.index):
        inv_idx[val] = pos
    sub = dec_obj.substitute
    buf = bytearray(data)
    n = len(buf)
    off = 0
    seq_idx = index

    def enc_byte(pos_in_buf: int, idx: int):
        b = (
            sub[((idx >> 2) & 3) + 4]
            + sub[idx & 3]
            + sub[((idx >> 4) & 3) + 8]
            + sub[(idx % 256 >> 6) + 12]
        )
        p_val = buf[pos_in_buf]
        lo = inv_idx[(p_val + b) & 0xF]
        hi = inv_idx[((p_val >> 4) + b) & 0xF]
        buf[pos_in_buf] = (hi << 4) | lo
        return p_val, idx + 1

    while off < n:
        idx = seq_idx
        cur, idx = enc_byte(off, idx)
        off += 1
        lit_len = cur >> 4
        match_len_nib = cur & 0xF
        if lit_len == 0xF:
            b = 0xFF
            while b == 0xFF:
                b, idx = enc_byte(off, idx)
                off += 1
                lit_len += b
        off += lit_len
        if off < n:
            _, idx = enc_byte(off, idx)
            off += 1
            _, idx = enc_byte(off, idx)
            off += 1
            if match_len_nib == 0xF:
                b = 0xFF
                while b == 0xFF:
                    b, idx = enc_byte(off, idx)
                    off += 1
        seq_idx += 1
    return bytes(buf)


def meta(raw: bytes):
    r = EndianBinaryReader(raw)
    r.read_string_to_null()
    r.read_u_int()
    r.read_string_to_null()
    r.read_string_to_null()
    hp = r.Position
    size = r.read_long()
    cs = r.read_u_int()
    us = r.read_u_int()
    fl = r.read_u_int()
    he = r.Position
    dec = asm.ArchiveStorageDecryptor(r) if fl & 0x400 else None
    ep = r.Position
    r.align_stream(16)
    start = r.Position
    bu = next(iter(UnityPy.load(raw).files.values()))
    ci = raw[size - cs : size] if fl & 128 else raw[start : start + cs]
    info = bu.decompress_data(ci, us, fl)
    count = struct.unpack_from(">I", info, 16)[0]
    p = start if fl & 128 else start + cs
    if fl & 512:
        p = (p + 15) // 16 * 16
    chunks = []
    for i in range(count):
        u, c, f = struct.unpack_from(">IIH", info, 20 + 10 * i)
        d = bu.decompress_data(raw[p : p + c], u, f, i)
        assert len(d) == u
        p += c
        chunks.append(d)
    return hp, he, ep, dec, info, b"".join(chunks)


def repack_unityfs(plain_bundle: bytes, original: bytes, slot: int, blocksize: int = 131072):
    hp, he, ep, _, info, plain = meta(plain_bundle)
    _, ohe, oep, odec, _, _ = meta(original)
    compressed = []
    entries = []
    for i, p in enumerate(range(0, len(plain), blocksize)):
        chunk = plain[p : p + blocksize]
        c = lz4.block.compress(chunk, mode="high_compression", compression=12, store_size=False)
        if len(c) >= len(chunk):
            c = chunk
            fl = 0
        else:
            c = encrypt_lz4(c, i, odec) if odec is not None else c
            fl = 0x103 if odec is not None else 0x03
        compressed.append(c)
        entries.append((len(chunk), len(c), fl))
    n = struct.unpack_from(">I", info, 16)[0]
    ni = (
        info[:16]
        + struct.pack(">I", len(entries))
        + b"".join(struct.pack(">IIH", *x) for x in entries)
        + info[20 + 10 * n :]
    )
    ci = lz4.block.compress(ni, mode="high_compression", compression=12, store_size=False)
    head = bytearray(original[:he])
    new_flags = 0x643 if odec is not None else 0x243
    struct.pack_into(">QIII", head, hp, slot, len(ci), len(ni), new_flags)
    out = head + original[ohe:oep]
    freepos = len(out)
    out.extend(bytes((-len(out)) % 16))
    hdr_pad = len(out) - freepos
    out += ci
    out.extend(bytes((-len(out)) % 16))
    out += b"".join(compressed)
    actual = len(out)
    if actual > slot:
        return None, {"compressed": actual, "slot": slot, "overflow": actual - slot}
    if hdr_pad >= 4:
        fixup_pos = freepos
    elif slot - actual >= 4:
        fixup_pos = actual
    else:
        return None, {"compressed": actual, "slot": slot, "error": "no 4-byte fixup slot"}
    out.extend(bytes(slot - len(out)))
    assert patch_crc(out, zlib.crc32(original) & 0xFFFFFFFF, fixup_pos)
    check = UnityPy.load(bytes(out))
    _, _, _, _, _, roundtrip = meta(bytes(out))
    assert roundtrip == plain
    return bytes(out), {
        "compressed": actual,
        "slot": slot,
        "padding": slot - actual,
        "fixup_offset": fixup_pos,
        "objects": len(list(check.objects)),
    }


def subset_ttf(font_bytes: bytes, corpus_cps: set[int]) -> tuple[bytes, dict]:
    f = TTFont(io.BytesIO(font_bytes))
    cmap = f.getBestCmap() or {}
    keep = set(cmap) & corpus_cps
    opt = subset.Options()
    opt.recalc_timestamp = False
    opt.retain_gids = False
    opt.notdef_glyph = True
    opt.notdef_outline = True
    sub = subset.Subsetter(options=opt)
    sub.populate(unicodes=keep)
    sub.subset(f)
    dest = io.BytesIO()
    f.save(dest)
    new_bytes = dest.getvalue()
    nf = TTFont(io.BytesIO(new_bytes))
    after_cmap = nf.getBestCmap() or {}
    missing = keep - set(after_cmap)
    assert all(cmap[cp] == ".notdef" for cp in missing), ("lost glyphs", sorted(missing))
    return new_bytes, {
        "old": len(font_bytes),
        "new": len(new_bytes),
        "kept_codepoints": len(keep),
        "original_codepoints": len(cmap),
    }
