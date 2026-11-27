# -*- coding: utf-8 -*-
"""Build VI fixed-size VStringPool and LRGB1001 language table .r files with exact CRC32."""
from array import array
from pathlib import Path
import hashlib
import json
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "crc"))
import vi_codec as V  # noqa: E402
import crcchain as C  # noqa: E402
from crcpatch import patch_crc  # noqa: E402

LIVE = Path(r"E:\YostarGames\AZUPRO_JP\AzurPromiliaJP_Data")
WORK = Path(r"C:\Users\Shimakaze\.gemini\antigravity\brain\6277206b-4249-4355-8158-74755c1fe94b\scratch\vi_build")
PAY = REPO / "payload-vi" / "jp_game"

POOL_REL = ".res/raw_base_package/BundleFiles/heqmts9lcjdvbupu0x2wpg.r"
TABLE_REL = ".res/raw_streaming_package/BundleFiles/5g1m5b4sbqlfalcxoaquw.r"


def read_orig(rel: str, expected_sha: str | None = None) -> bytes:
    for base in (LIVE, LIVE.parent / ".vi-jp-crc-readonly-3219598-backup", LIVE.parent / ".jp-crc-readonly-3219598-backup"):
        p = base / rel
        if p.is_file():
            b = p.read_bytes()
            if expected_sha is None or hashlib.sha256(b).hexdigest() == expected_sha:
                return b
    raise FileNotFoundError(f"Original baseline not found for {rel} ({expected_sha})")


def solve_columns(cols: list[int], rhs: int):
    basis = {}
    for i, value in enumerate(cols):
        mask = 1 << i
        while value:
            bit = value.bit_length() - 1
            if bit not in basis:
                basis[bit] = (value, mask)
                break
            v, m = basis[bit]
            value ^= v
            mask ^= m
    mask = 0
    while rhs:
        bit = rhs.bit_length() - 1
        if bit not in basis:
            raise ValueError("CRC permutation basis is not full rank")
        v, m = basis[bit]
        rhs ^= v
        mask ^= m
    return mask, len(basis)


def read_table_index(plain: bytes):
    pos = 0
    base_cnt = struct.unpack_from("<I", plain, pos)[0]
    pos += 4
    base_tabs = {}
    for _ in range(base_cnt):
        sz = struct.unpack_from("<I", plain, pos)[0]
        pos += 4
        name = plain[pos : pos + sz].decode("utf-8")
        pos += sz
        off = struct.unpack_from("<I", plain, pos)[0]
        pos += 4
        base_tabs[name] = off
    lang_cnt = struct.unpack_from("<I", plain, pos)[0]
    pos += 4
    langs = {}
    for _ in range(lang_cnt):
        lsz = struct.unpack_from("<I", plain, pos)[0]
        pos += 4
        lname = plain[pos : pos + lsz].decode("utf-8")
        pos += lsz
        tcnt = struct.unpack_from("<I", plain, pos)[0]
        pos += 4
        tabs = {}
        for _ in range(tcnt):
            tsz = struct.unpack_from("<I", plain, pos)[0]
            pos += 4
            tname = plain[pos : pos + tsz].decode("utf-8")
            pos += tsz
            toff = struct.unpack_from("<I", plain, pos)[0]
            pos += 4
            tabs[tname] = toff
        langs[lname] = tabs
    return base_tabs, langs, pos


def sanitize_translations() -> dict[str, str]:
    ast_unique = json.loads((WORK / "ast_unique.json").read_text("utf-8"))
    ast_vi_raw = json.loads((WORK / "ast_vi.json").read_text("utf-8"))
    vstr_unique = json.loads((WORK / "vstr_unique.json").read_text("utf-8"))
    vstr_vi_raw = json.loads((WORK / "vstr_vi.json").read_text("utf-8"))

    ph_re = re.compile(r"\{[0-9]+\}|%[sd]|\\n")
    mapping = {}

    def clean(src: str, vi: str) -> str:
        vi = vi.replace("\\xB7", "·").replace("\\xb7", "·")
        for p in ph_re.findall(src):
            if p not in vi:
                return src
        return vi

    for idx, src in enumerate(ast_unique):
        if str(idx) in ast_vi_raw:
            mapping[src] = clean(src, ast_vi_raw[str(idx)])
    for idx, (_, src) in enumerate(vstr_unique):
        if str(idx) in vstr_vi_raw:
            mapping[src] = clean(src, vstr_vi_raw[str(idx)])
    new_u_path = WORK / "new_3273853_unique.json"
    new_v_path = WORK / "new_3273853_vi.json"
    if new_u_path.is_file() and new_v_path.is_file():
        new_unique = json.loads(new_u_path.read_text("utf-8"))
        new_vi = json.loads(new_v_path.read_text("utf-8"))
        for idx, src in enumerate(new_unique):
            if str(idx) in new_vi:
                mapping[src] = clean(src, new_vi[str(idx)])
    return mapping


def build_pool(trans_map: dict[str, str], jp_kids: dict[int, str], src_sha: str | None = None):
    orig_raw = read_orig(POOL_REL, src_sha)
    plain = V.decode_mmap(orig_raw)
    ht, b0, os0, hs0, cap0, cnt0 = struct.unpack_from("<6I", plain, 0)
    st_total, st_base, st_offs, st_start, st_cnt = struct.unpack_from("<5I", plain, ht)
    assert cnt0 == st_cnt
    assert ht + st_total == len(plain)

    # Collect all original hash items
    b_offs = struct.unpack_from(f"<{cap0}I", plain, os0 - 4120)
    items = []
    for bo in b_offs:
        if bo == 0:
            continue
        p = bo - 4120
        cnt = struct.unpack_from("<I", plain, p)[0]
        for j in range(cnt):
            h, k = struct.unpack_from("<Qi", plain, p + 4 + 12 * j)
            items.append((h, k))

    old_string_offsets = array("I")
    old_string_offsets.frombytes(plain[st_offs - 4120 : st_start - 4120])
    old_string_payload = plain[st_start - 4120 :]

    # Deduplicate new Vietnamese strings and assign IDs starting at st_cnt
    vi_to_new_id: dict[str, int] = {}
    kid_map: dict[int, int] = {}
    new_offsets_rel = []
    new_payload = bytearray()
    cur_end = len(old_string_payload)

    for old_kid, jp_str in sorted(jp_kids.items()):
        vi_str = trans_map.get(jp_str)
        if not vi_str or vi_str == jp_str:
            continue
        if vi_str not in vi_to_new_id:
            new_id = st_cnt + len(vi_to_new_id)
            vi_to_new_id[vi_str] = new_id
            b = vi_str.encode("utf-8")
            new_offsets_rel.append(cur_end)
            new_payload += struct.pack("<i", len(b))
            new_payload += b
            cur_end += 4 + len(b)
        kid_map[old_kid] = vi_to_new_id[vi_str]

    new_cnt = st_cnt + len(vi_to_new_id)
    full_payload = old_string_payload + bytes(new_payload)
    string_total = 20 + 4 * new_cnt + len(full_payload)
    desired = len(orig_raw) - 4120
    hash_total = desired - string_total
    print(f"Pool: old_cnt={st_cnt}, added_unique_vi={len(vi_to_new_id)}, new_payload={len(new_payload)} B, hash_total={hash_total}")

    chosen = None
    for cap in (1048573, 786433, 524287, 393209, 262139, 196597, 131071, 65521):
        occupied = len({h % cap for h, _ in items})
        used = 24 + 4 * cap + 4 * occupied + 12 * len(items)
        if hash_total - used >= 4:
            chosen = (cap, used)
            break
    assert chosen is not None, f"No hash capacity fits! hash_total={hash_total}"
    cap, used = chosen
    padding = hash_total - used
    print(f"Chosen hash cap={cap}, used={used}, padding={padding}")

    buckets: dict[int, list[tuple[int, int]]] = {}
    for h, k in items:
        buckets.setdefault(h % cap, []).append((h, k))

    hash_start = 4120 + 24 + 4 * cap
    offsets = array("I", [0]) * cap
    bucket_payload = bytearray()
    for bi, entries in sorted(buckets.items()):
        offsets[bi] = hash_start + len(bucket_payload)
        bucket_payload += struct.pack("<I", len(entries))
        for h, k in entries:
            bucket_payload += struct.pack("<Qi", h, k)
    assert 24 + len(offsets) * 4 + len(bucket_payload) == used

    new_string_start = 4120 + hash_total + 20 + 4 * new_cnt
    delta = new_string_start - st_start
    all_offsets = array("I", (x + delta for x in old_string_offsets))
    all_offsets.extend(new_string_start + rel for rel in new_offsets_rel)
    assert len(all_offsets) == new_cnt

    raw_plain = (
        struct.pack("<6I", hash_total, 4120, 4144, hash_start, cap, new_cnt)
        + offsets.tobytes()
        + bytes(bucket_payload)
        + bytes(padding)
        + struct.pack("<5I", string_total, 4120 + hash_total, 4120 + hash_total + 20, new_string_start, new_cnt)
        + all_offsets.tobytes()
        + full_payload
    )
    assert len(raw_plain) == desired

    candidate = bytearray(V.encode_mmap(raw_plain, orig_raw))
    target_crc = zlib.crc32(orig_raw) & 0xFFFFFFFF
    fixup = 4120 + used
    assert patch_crc(candidate, target_crc, fixup), "Pool patch_crc failed"
    assert len(candidate) == len(orig_raw)
    assert (zlib.crc32(bytes(candidate)) & 0xFFFFFFFF) == target_crc

    dest = PAY / POOL_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(candidate))

    # Roundtrip check (excluding the 4-byte CRC32 fixup inside unused hash padding)
    chk = V.decode_mmap(bytes(candidate))
    assert chk[:used] == raw_plain[:used] and chk[used + 4 :] == raw_plain[used + 4 :]
    mp = LIVE / ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3273853.bytes"
    assert not C.verify(mp.read_bytes(), dest)
    print("[OK] VStringPool CRC & manifest verified!")
    return kid_map, vi_to_new_id


def build_table(kid_map: dict[int, int], src_sha: str | None = None):
    orig_raw = read_orig(TABLE_REL, src_sha)
    source_plain = V.decode_mmap(orig_raw)
    plain = bytearray(source_plain)
    si = read_table_index(source_plain)

    # Remap every jp table VStringId
    remapped = 0
    for tname, toff in si[1]["jp"].items():
        p = toff - 4120
        n = struct.unpack_from("<I", plain, p)[0]
        t_start = p + 4
        c, r, *lens = struct.unpack_from(">6I", plain, t_start + 8)
        s = t_start + 36 + sum(lens)
        idx_type, idx_sz = struct.unpack_from("<II", plain, s)
        d_pos = s + 8 + idx_sz
        d_end = t_start + n
        for pos in range(d_pos, d_end, 12):
            old_kid = struct.unpack_from("<i", plain, pos + 8)[0]
            new_kid = kid_map.get(old_kid)
            if new_kid is not None:
                struct.pack_into("<i", plain, pos + 8, new_kid)
                remapped += 1
    print(f"Table: remapped {remapped} jp row string IDs")

    # Balance CRC32 via disjoint adjacent base-table index entry swaps
    n_idx = struct.unpack_from("<I", plain, 0)[0]
    pos = 4
    entries = []
    for _ in range(n_idx):
        start = pos
        sz = struct.unpack_from("<I", plain, pos)[0]
        pos += 4 + sz + 4
        entries.append((start, pos))
    swaps = []
    for i in range(0, min(192, len(entries) - 1), 2):
        a, m = entries[i]
        _, b = entries[i + 1]
        swaps.append((a, b, bytes(plain[m:b] + plain[a:m])))

    cand = bytearray(V.encode_mmap(bytes(plain), orig_raw))
    base_crc = zlib.crc32(cand) & 0xFFFFFFFF
    cols = []
    for a, b, repl in swaps:
        q = 4120 + a
        r = 4120 + b
        saved = bytes(cand[q:r])
        diff = bytes(x ^ y for x, y in zip(plain[a:b], repl))
        cand[q:r] = bytes(x ^ y for x, y in zip(saved, diff))
        cols.append((zlib.crc32(cand) & 0xFFFFFFFF) ^ base_crc)
        cand[q:r] = saved

    orig_crc = zlib.crc32(orig_raw) & 0xFFFFFFFF
    mask, rank = solve_columns(cols, orig_crc ^ base_crc)
    swapped = 0
    for i, (a, b, repl) in enumerate(swaps):
        if (mask >> i) & 1:
            plain[a:b] = repl
            swapped += 1

    assert read_table_index(bytes(plain)) == si
    final_cand = V.encode_mmap(bytes(plain), orig_raw)
    assert len(final_cand) == len(orig_raw)
    assert (zlib.crc32(final_cand) & 0xFFFFFFFF) == orig_crc

    dest = PAY / TABLE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(final_cand)
    assert V.decode_mmap(final_cand) == bytes(plain)
    mp = LIVE / ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3273853.bytes"
    assert not C.verify(mp.read_bytes(), dest)
    print(f"[OK] Language tables CRC & manifest verified! rank={rank}, swaps={swapped}")


def extract_live_jp_kids(pool_raw: bytes, table_raw: bytes) -> dict[int, str]:
    pool_plain = V.decode_mmap(pool_raw)
    table_plain = V.decode_mmap(table_raw)
    ht, _, _, _, _, _ = struct.unpack_from("<6I", pool_plain, 0)
    _, _, st_offs, _, st_cnt = struct.unpack_from("<5I", pool_plain, ht)
    offs = struct.unpack_from(f"<{st_cnt}I", pool_plain, st_offs - 4120)
    si = read_table_index(table_plain)
    jp_kids: dict[int, str] = {}
    for _, toff in si[1]["jp"].items():
        p = toff - 4120
        n = struct.unpack_from("<I", table_plain, p)[0]
        t_start = p + 4
        _, _, *lens = struct.unpack_from(">6I", table_plain, t_start + 8)
        s = t_start + 36 + sum(lens)
        _, idx_sz = struct.unpack_from("<II", table_plain, s)
        d_pos = s + 8 + idx_sz
        d_end = t_start + n
        for pos in range(d_pos, d_end, 12):
            kid = struct.unpack_from("<i", table_plain, pos + 8)[0]
            if 0 <= kid < st_cnt and kid not in jp_kids:
                o = offs[kid] - 4120
                slen = struct.unpack_from("<i", pool_plain, o)[0]
                if slen > 0:
                    val = pool_plain[o + 4 : o + 4 + slen].decode("utf-8", "replace")
                    if val:
                        jp_kids[kid] = val
    return jp_kids


def main():
    pool_sha = "60e09fa31ac7e43e2a74cb7e722cf19b3331a188817125a086a57a17a34987ee"
    table_sha = "4369839fd46cd2c821f33dc2b92c46cc87f4413a215be0abe17461ec743896c2"
    orig_pool = read_orig(POOL_REL, pool_sha)
    orig_table = read_orig(TABLE_REL, table_sha)
    jp_kids = extract_live_jp_kids(orig_pool, orig_table)
    trans_map = sanitize_translations()
    print(f"Loaded {len(trans_map)} translations for {len(jp_kids)} non-empty JP kids")
    kid_map, _ = build_pool(trans_map, jp_kids, pool_sha)
    build_table(kid_map, table_sha)


if __name__ == "__main__":
    main()
