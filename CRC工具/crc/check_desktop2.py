import sys, hashlib, zlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
# 每个 .r 文件 -> 到对应清单里找 pack，核对 size/crc
pairs = [
 (".res/default_package/BundleFiles", ".res/default_package/ManifestFiles/0release_default_package_3221745.bytes"),
 (".res/raw_base_package/BundleFiles", ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes"),
 (".res/raw_streaming_package/BundleFiles", ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes"),
 ("StreamingAssets/.res/default_package", "StreamingAssets/.res/default_package/0release_default_package_3060618.bytes"),
 ("StreamingAssets/.res/static_package", "StreamingAssets/.res/static_package/0release_static_package_3060618.bytes"),
]
for bdir, mfp in pairs:
    d = P/bdir
    if not d.exists(): continue
    mf = P/mfp
    m = C.parse(mf.read_bytes())
    idx = {}
    for pk in m["packs"]:
        idx[C.name_of(pk)] = pk
    for f in sorted(d.glob("*.r")):
        key = f.stem
        pk = idx.get(key)
        data = f.read_bytes()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        if pk is None:
            print("  NOT-IN-MANIFEST", bdir, f.name); continue
        ok = (len(data)==pk["size"] and crc==pk["crc"])
        print("  %-46s size %10d/%-10d crc %08x/%08x  %s" % (f.name, len(data), pk["size"], crc, pk["crc"], "OK" if ok else "MISMATCH"))
