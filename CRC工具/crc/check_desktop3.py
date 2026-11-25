import sys, hashlib, zlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
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
    m = C.parse((P/mfp).read_bytes())
    idx = {C.name_of(pk): pk for pk in m["packs"]}
    print("="*18, bdir)
    for f in sorted(d.glob("*.r")):
        key = f.stem
        pk = idx.get(key)
        data = f.read_bytes()
        crc = zlib.crc32(data) & 0xFFFFFFFF
        if pk is None:
            print("   %-40s NOT-IN-MANIFEST" % f.name); continue
        # 该 pack 里的 bundle 段
        pi = m["packs"].index(pk)
        segs = C.segments(m, pi)
        seg_ok = all(len(data[o:o+s])==s and (zlib.crc32(data[o:o+s])&0xFFFFFFFF)==m["bundles"][bi]["crc"] for bi,o,s in segs)
        ok = (len(data)==pk["size"] and crc==pk["crc"] and seg_ok)
        print("   %-40s size %9d/%-9d crc %08x/%08x segs=%d %s" % (f.name, len(data), pk["size"], crc, pk["crc"], len(segs), "OK" if ok else "MISMATCH"))
