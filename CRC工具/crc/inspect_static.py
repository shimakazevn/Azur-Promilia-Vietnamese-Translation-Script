import sys, zlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
mf = P/"StreamingAssets/.res/static_package/0release_static_package_3060618.bytes"
m = C.parse(mf.read_bytes())
print("name_style", m["name_style"], "bundle_type", m["bundle_type"], "packs", len(m["packs"]), "bundles", len(m["bundles"]))
for i,pk in enumerate(m["packs"]):
    print(i, repr(C.name_of(pk)), "size", pk["size"], "crc", hex(pk["crc"]), "hashpair", hex(pk["hash0"]), hex(pk["hash1"]))
