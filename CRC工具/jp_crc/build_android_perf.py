# -*- coding: utf-8 -*-
"""Build Android In-Game Graphics Unlock & Performance Config `.r` with exact CRC32."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import vi_codec as V  # noqa: E402
from build_vi_raw import read_table_index, solve_columns  # noqa: E402

TABLE_REL = "raw_streaming_package/BundleFiles/lgljnx3smdqqqfkgr8obq.r"
ANDROID_DEPLOY_JSON = REPO / "tools" / "android-deployment-vi.json"
ANDROID_BASE_VI = REPO / "payload-vi" / "android_game" / TABLE_REL
ANDROID_PERF_OUT = REPO / "payload-vi" / "android_perf" / TABLE_REL
ANDROID_PERF_JSON = REPO / "tools" / "android-perf-vi.json"


def _load_pool_lookup(pool_path: Path) -> tuple[dict[str, int], list[str | None]]:
    """Return (string -> kid, kid -> string) lookup from Android VI VStringPool."""
    plain = V.decode_mmap(pool_path.read_bytes())
    ht = struct.unpack_from("<I", plain, 0)[0]
    st_cnt = struct.unpack_from("<5I", plain, ht)[4]
    offsets = struct.unpack_from(f"<{st_cnt}I", plain, ht + 20)
    by_id: list[str | None] = [None] * st_cnt
    by_str: dict[str, int] = {}
    for kid in range(st_cnt):
        p = offsets[kid] - 4120
        ln = struct.unpack_from("<i", plain, p)[0]
        if ln >= 0:
            val = plain[p + 4 : p + 4 + ln].decode("utf-8", "replace")
            by_id[kid] = val
            by_str.setdefault(val, kid)
    return by_str, by_id


def _table_rows_span(plain: bytearray, toff: int) -> tuple[int, int, list[int]]:
    """Return (stride, dp, pks) for an LRGB1001 base table."""
    p = toff - 4120
    t_start = p + 4
    lens = struct.unpack_from(">6I", plain, t_start + 8)[2:]
    s = t_start + 36 + sum(lens)
    stride, isz = struct.unpack_from("<II", plain, s)
    pks = list(struct.unpack_from(f"<{isz // 4}i", plain, s + 8))
    return stride, s + 8 + isz, pks


def _patch_option_tables(plain: bytearray, by_str: dict[str, int], base_tabs: dict[str, int]) -> None:
    """Unlock hidden PC/Mobile graphics knobs and clean Mobile Perf/Balance defaults cleanly."""
    kid_1 = by_str["1"]
    kid_12 = by_str["1|2"]

    # optionData columns used here:
    # 2=isActive, 3=isShow, 14=defaultPara(kid), 17=allowChange, 19=clientType(kid)
    stride, dp, pks = _table_rows_span(plain, base_tabs["optionData"])
    pk_idx = {pk: i for i, pk in enumerate(pks)}

    # Unlock mobile access (clientType='1|2') and ensure visible/changeable:
    # 38: Render Scale (50%-170%), 99: GI, 100: AO, 101: Reflections, 102: DoF,
    # 115: LightShaft, 117: LensFlare, 118: UVDistort, 123: Shadow Type (ASM|CSM)
    unlock_active = {38, 86, 87, 99, 100, 101, 102, 115, 117, 118, 123}
    unlock_ctype_both = {38, 86, 87, 99, 100, 101, 102, 115, 117, 118}
    set_def_one = {42, 86, 99, 100, 101, 102, 115, 116, 117, 118}

    for oid in unlock_active | unlock_ctype_both | set_def_one:
        row_off = dp + pk_idx[oid] * stride
        vals = list(struct.unpack_from(f"<{stride // 4}i", plain, row_off))
        if oid in unlock_active:
            vals[2] = 1
            vals[3] = 1
            vals[17] = 1
        if oid in unlock_ctype_both:
            vals[19] = kid_12
        if oid in set_def_one:
            # Make OFF/Low selectable as fallback default when preset switches to Custom
            vals[14] = kid_1
        struct.pack_into(f"<{stride // 4}i", plain, row_off, *vals)

    # Also ensure optionData_total_mobile keeps Balance (L3) smoother on hidden FX
    # while keeping Ultra (L4) clean and Performance (L2) maximum FPS.
    m_stride, m_dp, m_pks = _table_rows_span(plain, base_tabs["optionData_total_mobile"])
    for idx, pk in enumerate(m_pks):
        row_off = m_dp + idx * m_stride
        oid, l2, l3, l4, l5 = struct.unpack_from("<5i", plain, row_off)
        if oid in (99, 100, 101, 114):
            l3 = 1
        elif oid in (115, 116, 117, 118):
            l2 = 1
            l3 = 1
        struct.pack_into("<5i", plain, row_off, oid, l2, l3, l4, l5)


def _balance_crc_by_header_swaps(plain: bytearray, orig_raw: bytes, orig_crc: int) -> bytes:
    """Match orig_crc exactly by permuting disjoint adjacent base-table index header pairs."""
    n_idx = struct.unpack_from("<I", plain, 0)[0]
    pos = 4
    entries: list[tuple[int, int]] = []
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

    mask, rank = solve_columns(cols, orig_crc ^ base_crc)
    swapped = 0
    for i, (a, b, repl) in enumerate(swaps):
        if (mask >> i) & 1:
            plain[a:b] = repl
            swapped += 1

    final_raw = V.encode_mmap(bytes(plain), orig_raw)
    assert len(final_raw) == len(orig_raw)
    assert (zlib.crc32(final_raw) & 0xFFFFFFFF) == orig_crc
    assert V.decode_mmap(final_raw) == bytes(plain)
    print(f"[OK] Balanced Android Perf CRC32={orig_crc} (rank={rank}, swaps={swapped})")
    return final_raw


def build() -> None:
    deploy = json.loads(ANDROID_DEPLOY_JSON.read_text("utf-8-sig"))
    entry = next(f for f in deploy["files"] if f["relative_path"] == TABLE_REL)
    pool_rel = next(
        f["relative_path"]
        for f in deploy["files"]
        if f["relative_path"].startswith("raw_base_package/") and f["size"] > 50_000_000
    )
    pool_path = REPO / "payload-vi" / "android_game" / pool_rel
    if not pool_path.is_file() or not ANDROID_BASE_VI.is_file():
        raise FileNotFoundError("Missing payload-vi/android_game baseline files.")

    base_bytes = ANDROID_BASE_VI.read_bytes()
    base_sha = hashlib.sha256(base_bytes).hexdigest()
    if base_sha != entry["target_sha256"]:
        raise ValueError(f"Base VI table hash mismatch: {base_sha} != {entry['target_sha256']}")

    by_str, _ = _load_pool_lookup(pool_path)
    src_plain = V.decode_mmap(base_bytes)
    plain = bytearray(src_plain)
    base_tabs, langs, _ = read_table_index(src_plain)

    _patch_option_tables(plain, by_str, base_tabs)
    final_raw = _balance_crc_by_header_swaps(plain, base_bytes, entry["crc32"])

    dec_tabs, dec_langs, _ = read_table_index(V.decode_mmap(final_raw))
    assert dec_tabs == base_tabs
    assert dec_langs == langs

    ANDROID_PERF_OUT.parent.mkdir(parents=True, exist_ok=True)
    ANDROID_PERF_OUT.write_bytes(final_raw)
    perf_sha = hashlib.sha256(final_raw).hexdigest()

    meta = {
        "schema_version": 1,
        "package_name": deploy["package_name"],
        "resource_version": deploy["resource_version"],
        "relative_path": TABLE_REL,
        "size": len(final_raw),
        "crc32": entry["crc32"],
        "source_sha256": entry["source_sha256"],
        "base_vi_sha256": entry["target_sha256"],
        "target_sha256": perf_sha,
        "unlocked_options": [
            "Tỷ lệ kết xuất 50%-170% (id=38)",
            "SSAA OFF / DLSS / FSR / XeSS (id=86,87)",
            "Chiếu sáng toàn cục / GI (id=99)",
            "Chất lượng AO (id=100)",
            "Chất lượng phản chiếu (id=101)",
            "Độ sâu trường ảnh / DoF (id=102)",
            "LightShaft / LensFlare / UVDistort (id=115,117,118)",
            "Loại bóng đổ ASM|CSM (id=123)",
        ],
    }
    ANDROID_PERF_JSON.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Wrote {ANDROID_PERF_OUT} ({len(final_raw)} bytes, sha256={perf_sha})")


if __name__ == "__main__":
    build()
