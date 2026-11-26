# -*- coding: utf-8 -*-
"""Build all 9 non-raw VI JP payload files (resources.assets + 8 UnityFS .r bundles)."""
from pathlib import Path
import hashlib
import io
import json
import re
import shutil
import struct
import sys
import zlib

from fontTools.ttLib import TTFont
import UnityPy

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "crc"))
import vi_codec as V  # noqa: E402
import crcchain as C  # noqa: E402

LIVE = Path(r"E:\YostarGames\AZUPRO_JP\AzurPromiliaJP_Data")
WORK = Path(r"C:\Users\Shimakaze\.gemini\antigravity\brain\6277206b-4249-4355-8158-74755c1fe94b\scratch\vi_build")
PAY = REPO / "payload-vi" / "jp_game"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_orig(rel: str, expected_sha: str | None = None) -> bytes:
    candidates = [
        LIVE / rel,
        LIVE.parent / ".vi-jp-crc-readonly-3219598-backup" / rel,
        LIVE.parent / ".jp-crc-readonly-3219598-backup" / rel,
    ]
    for p in candidates:
        if p.is_file():
            b = p.read_bytes()
            if expected_sha is None or sha256(b) == expected_sha:
                return b
    raise FileNotFoundError(f"Original baseline not found for {rel} (expected {expected_sha})")


def build_corpus() -> set[int]:
    vi_data = json.loads((HERE / "corpus_codepoints_vi.json").read_text("utf-8"))
    pts = set(vi_data["codepoints"]) | set(range(32, 127)) | set(range(0x3000, 0x3100)) | set(range(0xFF00, 0xFFF0))
    for lead in range(0xA1, 0xFF):
        for trail in range(0xA1, 0xFF):
            try:
                pts.update(map(ord, bytes([lead, trail]).decode("euc_jp")))
            except UnicodeDecodeError:
                pass
    # Include every character appearing in AST, VStringPool, and builtin CSV
    for f in (WORK / "ast_vi.json", WORK / "builtInLangString_vi.csv", WORK / "vstr_vi.json"):
        if f.exists():
            pts.update(map(ord, f.read_text("utf-8")))
    return pts


def sanitize_ast(ast_unique: list[str], ast_vi_raw: dict[str, str]) -> dict[str, str]:
    mapping = {}
    ph_re = re.compile(r"\{[0-9]+\}|%[sd]|<[^>]+>|\\n")
    for idx, src in enumerate(ast_unique):
        vi = ast_vi_raw[str(idx)]
        vi = vi.replace("\\xB7", "·").replace("\\xb7", "·")
        # Ensure placeholders present in src weren't dropped
        src_ph = ph_re.findall(src)
        for p in src_ph:
            if p.startswith("<ruby") or p == "</ruby>":
                continue
            if p not in vi:
                # Fallback to keeping src if tag got mangled
                if p.startswith("{") or p.startswith("%"):
                    vi = src
                    break
        mapping[src] = vi
    return mapping


def build_resources_assets(plan_entry: dict):
    src = read_orig("resources.assets", plan_entry["source_sha256"])
    env = UnityPy.load(src)
    vi_csv = (WORK / "builtInLangString_vi.csv").read_bytes()
    changed = 0
    for o in env.objects:
        if o.type.name == "TextAsset":
            t = o.read_typetree()
            if t.get("m_Name") == "builtInLangString":
                t["m_Script"] = vi_csv.decode("utf-8")
                o.save_typetree(t)
                changed += 1
    assert changed == 1
    saved = bytearray(env.file.save())
    unpadded = len(saved)
    assert unpadded <= len(src), f"resources.assets overflow: {unpadded} > {len(src)}"
    saved.extend(bytes(len(src) - unpadded))
    version = struct.unpack_from(">I", saved, 8)[0]
    if version >= 22:
        struct.pack_into(">q", saved, 24, len(saved))
    else:
        struct.pack_into(">I", saved, 4, len(saved))
    dest = PAY / "resources.assets"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(bytes(saved))
    # Roundtrip check
    chk = UnityPy.load(bytes(saved))
    assert any(o.type.name == "TextAsset" and o.read_typetree().get("m_Name") == "builtInLangString" for o in chk.objects)
    print(f"[OK] resources.assets unpadded={unpadded}/{len(src)}")


def adjust_noheight_metrics(font_bytes: bytes) -> bytes:
    f = TTFont(io.BytesIO(font_bytes))
    if "hhea" in f:
        f["hhea"].lineGap = 0
    if "OS/2" in f:
        f["OS/2"].sTypoLineGap = 0
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


def main():
    PAY.mkdir(parents=True, exist_ok=True)
    plan = json.loads((REPO / "tools" / "jp-deployment-vi.json").read_text("utf-8-sig"))
    entries = {e["relative_path"]: e for e in plan["files"]}

    ast_unique = json.loads((WORK / "ast_unique.json").read_text("utf-8"))
    ast_vi_raw = json.loads((WORK / "ast_vi.json").read_text("utf-8"))
    ast_map = sanitize_ast(ast_unique, ast_vi_raw)
    corpus = build_corpus()

    # 1. resources.assets
    build_resources_assets(entries["resources.assets"])

    # 2. Extract full VI-capable a00, b00, c00 from static_package/6pq4a7hlp7zidu91dvvww.r
    stat_rel = "StreamingAssets/.res/static_package/6pq4a7hlp7zidu91dvvww.r"
    stat_orig = read_orig(stat_rel, entries[stat_rel]["source_sha256"])
    e_stat = UnityPy.load(stat_orig)
    full_fonts = {}
    for o in e_stat.objects:
        if o.type.name == "Font":
            t = o.read_typetree()
            if t["m_Name"] in ("a00", "b00", "c00"):
                full_fonts[t["m_Name"]] = bytes(t["m_FontData"])

    sub_fonts = {}
    for fname in ("a00", "b00", "c00"):
        sub_b, info = V.subset_ttf(full_fonts[fname], corpus)
        sub_fonts[fname] = sub_b
        print(f"  Subset {fname}: {info}")
    sub_fonts["a00_jp_input_noheight"] = adjust_noheight_metrics(sub_fonts["a00"])
    sub_fonts["b00_jp_input_noheight"] = adjust_noheight_metrics(sub_fonts["b00"])

    # 3. Update 6pq4a7hlp7zidu91dvvww.r (updatableBuiltInLangString + subsetted a00/b00/c00)
    up_csv = (WORK / "updatableBuiltInLangString_vi.csv").read_text("utf-8")
    for o in e_stat.objects:
        if o.type.name == "TextAsset":
            t = o.read_typetree()
            if t.get("m_Name") == "updatableBuiltInLangString":
                t["m_Script"] = up_csv
                o.save_typetree(t)
        elif o.type.name == "Font":
            t = o.read_typetree()
            nm = t.get("m_Name", "")
            if nm in ("a00", "b00", "c00"):
                t["m_FontData"] = list(sub_fonts[nm])
                o.save_typetree(t)
    stat_plain = next(iter(e_stat.files.values())).save(packer="lz4")
    stat_out, stat_rep = V.repack_unityfs(stat_plain, stat_orig, len(stat_orig))
    assert stat_out is not None, stat_rep
    dest = PAY / stat_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(stat_out)
    print(f"[OK] {stat_rel}: {stat_rep}")

    # 4. Font bundles in StreamingAssets/.res/default_package/
    font_bundles = [
        ("StreamingAssets/.res/default_package/xlpsyuxnoz1cjmawi1wcxa.r", "a00"),
        ("StreamingAssets/.res/default_package/e5e4oijae8zliat91bgbw.r", "a00_jp_input_noheight"),
        ("StreamingAssets/.res/default_package/awcxxitzquckttvmx0c5q.r", "b00"),
        ("StreamingAssets/.res/default_package/hqqoy0ojvzpggukcf5m85w.r", "b00_jp_input_noheight"),
    ]
    for rel, font_key in font_bundles:
        e_entry = entries[rel]
        orig = read_orig(rel, e_entry["source_sha256"])
        out_buf = bytearray(orig)
        seg0 = e_entry["segments"][0]
        seg_orig = orig[seg0["offset"] : seg0["offset"] + seg0["size"]]
        env = UnityPy.load(seg_orig)
        replaced = 0
        for o in env.objects:
            if o.type.name == "Font":
                t = o.read_typetree()
                t["m_FontData"] = list(sub_fonts[font_key])
                o.save_typetree(t)
                replaced += 1
        assert replaced == 1
        plain = next(iter(env.files.values())).save(packer="lz4")
        seg_new, rep = V.repack_unityfs(plain, seg_orig, seg0["size"])
        assert seg_new is not None, (rel, rep)
        out_buf[seg0["offset"] : seg0["offset"] + seg0["size"]] = seg_new
        dest = PAY / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bytes(out_buf))
        print(f"[OK] {rel}: {rep}")

    # 5. c00 bundle (rpgxilrqhjgj9am5g799fa.r) - check VI coverage in original c00; keep original if 100% VI covered, else subset full c00
    c00_rel = "StreamingAssets/.res/default_package/rpgxilrqhjgj9am5g799fa.r"
    c00_orig = read_orig(c00_rel, entries[c00_rel]["source_sha256"])
    e_c00 = UnityPy.load(c00_orig)
    c00_need_replace = False
    for o in e_c00.objects:
        if o.type.name == "Font":
            t = o.read_typetree()
            f = TTFont(io.BytesIO(bytes(t["m_FontData"])))
            cm = set(f.getBestCmap() or {})
            vi_chars = set(json.loads((HERE / "corpus_codepoints_vi.json").read_text("utf-8"))["codepoints"])
            missing_vi = {cp for cp in vi_chars if cp < 0x3000} - cm
            print(f"  Original c00 missing latin/vi codepoints (<0x3000): {len(missing_vi)}")
            if missing_vi:
                c00_need_replace = True
    dest = PAY / c00_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not c00_need_replace:
        dest.write_bytes(c00_orig)
        print(f"[OK] {c00_rel}: original c00 already covers all VI codepoints, copied intact")
    else:
        for o in e_c00.objects:
            if o.type.name == "Font":
                t = o.read_typetree()
                t["m_FontData"] = list(sub_fonts["c00"])
                o.save_typetree(t)
        plain = next(iter(e_c00.files.values())).save(packer="lz4")
        c00_new, rep = V.repack_unityfs(plain, c00_orig, len(c00_orig))
        assert c00_new is not None, rep
        dest.write_bytes(c00_new)
        print(f"[OK] {c00_rel}: {rep}")

    # 6. ast_staticTextKeyConfig bundles (yr49bxop0f3reujfsmyfca.r & tqells6pca8ieju9qlbuw.r)
    for rel in (".res/default_package/BundleFiles/yr49bxop0f3reujfsmyfca.r", "StreamingAssets/.res/default_package/tqells6pca8ieju9qlbuw.r"):
        e_entry = entries[rel]
        orig = read_orig(rel, e_entry["source_sha256"])
        out_buf = bytearray(orig)
        target_seg = next(s for s in e_entry["segments"] if s["bundle_index"] in (369167, 342724))
        seg_orig = orig[target_seg["offset"] : target_seg["offset"] + target_seg["size"]]
        env = UnityPy.load(seg_orig)
        updated = 0
        for o in env.objects:
            if o.type.name == "MonoBehaviour" and o.path_id == -1792657902486032720:
                t = o.read_typetree()
                for item in t["list"]:
                    val = item["value"]
                    if val in ast_map:
                        item["value"] = ast_map[val]
                        updated += 1
                o.save_typetree(t)
        assert updated > 0
        plain = next(iter(env.files.values())).save(packer="lz4")
        seg_new, rep = V.repack_unityfs(plain, seg_orig, target_seg["size"], blocksize=262144)
        assert seg_new is not None, (rel, rep)
        out_buf[target_seg["offset"] : target_seg["offset"] + target_seg["size"]] = seg_new
        dest = PAY / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(bytes(out_buf))
        print(f"[OK] {rel}: updated={updated}, {rep}")

    # 7. Verify CRC32 and segments of all 8 UnityFS .r files against manifest
    for rel, e_entry in entries.items():
        if not rel.endswith(".r") or "raw_" in rel:
            continue
        p = PAY / rel
        data = p.read_bytes()
        assert len(data) == e_entry["size"], (rel, len(data), e_entry["size"])
        assert (zlib.crc32(data) & 0xFFFFFFFF) == e_entry["crc32"], (rel, "pack crc")
        for seg in e_entry["segments"]:
            scrc = zlib.crc32(data[seg["offset"] : seg["offset"] + seg["size"]]) & 0xFFFFFFFF
            assert scrc == seg["crc32"], (rel, seg["bundle_index"], "seg crc")
    print("ALL 9 NON-RAW FILES BUILT AND CRC32-VERIFIED!")


if __name__ == "__main__":
    main()
