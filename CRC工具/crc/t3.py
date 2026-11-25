import sys, zlib, hashlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

W = Path(r"C:\Users\xiaoxi\Documents\Codex\2026-11-24\new-chat\work")
# 上一轮已做过的补丁：raw_streaming_package 的 3iffxeedh2grvnbn2iag.r
orig_pack = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\.res\raw_streaming_package\BundleFiles\3iffxeedh2grvnbn2iag.r")
orig_mf = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\.res\raw_streaming_package\ManifestFiles\0release_raw_streaming_package_3221745.bytes")
patched_pack = W/"official_game_patch_v3"/".res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r"
patched_mf = W/"official_game_patch_v6"/".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes"
patched_hash = W/"official_game_patch_v6"/".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.hash"

for p in [orig_pack, orig_mf, patched_pack, patched_mf, patched_hash]:
    print(p.exists(), p.name)

om = orig_mf.read_bytes(); pm = patched_mf.read_bytes()
print("orig manifest ok:", C.verify(om, orig_pack) == [])
print("patched manifest vs patched pack:", C.verify(pm, patched_pack))
# 用工具重新算一遍，看是否与既有补丁的清单一致
newp, newm, newh, rep = C.rebuild(om, orig_pack, {})
print("rebuild identical to patched pack:", newp == patched_pack.read_bytes())
print("hash file matches md5:", patched_hash.read_text().strip() == hashlib.md5(pm).hexdigest())
mp = C.parse(pm); mo = C.parse(om)
print("pack crc old", hex(rep["oldPackCrc"]), "new(calculated)", hex(rep["newPackCrc"]))
pi = rep["packIndex"]; print("patched manifest pack crc:", hex(mp["packs"][pi]["crc"]), "size", mp["packs"][pi]["size"])
print("patched bytes len", len(patched_pack.read_bytes()))
print("manifest file identical:", newm == pm)
