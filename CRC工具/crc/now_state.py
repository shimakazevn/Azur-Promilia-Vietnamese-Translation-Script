# -*- coding: utf-8 -*-
import sys, hashlib, zlib, json
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
import crcchain as C

DATA = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
BK   = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")

pk = [
 (".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes", ".res/raw_streaming_package/BundleFiles", "3iffxeedh2grvnbn2iag.r"),
 (".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes", ".res/raw_base_package/BundleFiles", "v0k2cafcxjxawklow6skg.r"),
 (".res/default_package/ManifestFiles/0release_default_package_3221745.bytes", ".res/default_package/BundleFiles", "owmxh3bjdhcwjoabqv67q.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "StreamingAssets/.res/default_package", "a66pm5ie1rrjguuzlsyq.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "StreamingAssets/.res/default_package", "p4hifvtlpthiunufa1lslg.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "StreamingAssets/.res/default_package", "db0aboccfhk0ruhzeueydq.r"),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", "StreamingAssets/.res/static_package", "nkewfips4anrz2bqfjhpg.r"),
]
print("%-32s %-6s %-10s %-10s %-6s %-6s" % ("pack","侧","实际size","清单size","实际crc","一致"))
for mfp, bdir, name in pk:
    for tag, root in (("NOW", DATA), ("BAK", BK)):
        mp = root/mfp
        f  = root/bdir/name
        if not (mp.exists() and f.exists()):
            print("%-32s %-6s 缺文件" % (name, tag)); continue
        m = C.parse(mp.read_bytes())
        rec = [x for x in m["packs"] if C.name_of(x)==name]
        if not rec: print("%-32s %-6s 清单无此 pack" % (name, tag)); continue
        rec = rec[0]
        d = f.read_bytes()
        ok = len(d)==rec["size"] and (zlib.crc32(d)&0xFFFFFFFF)==rec["crc"]
        print("%-32s %-6s %-10d %-10d %08x %s" % (name, tag, len(d), rec["size"], zlib.crc32(d)&0xFFFFFFFF, "OK" if ok else "差异"))
