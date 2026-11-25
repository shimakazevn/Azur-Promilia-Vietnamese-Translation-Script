# -*- coding: utf-8 -*-
import sys, hashlib, zlib
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
import crcchain as C

DATA = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
BK   = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")

pairs = [
 (".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes", "3iffxeedh2grvnbn2iag.r"),
 (".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes", "v0k2cafcxjxawklow6skg.r"),
 (".res/default_package/ManifestFiles/0release_default_package_3221745.bytes", "owmxh3bjdhcwjoabqv67q.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "a66pm5ie1rrjguuzlsyq.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "p4hifvtlpthiunufa1lslg.r"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "db0aboccfhk0ruhzeueydq.r"),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", "nkewfips4anrz2bqfjhpg.r"),
]
print("%-32s %-4s %-11s %-10s %-4s %-6s %-5s" % ("pack","侧","size","crc","段","enc","refcnt"))
for mfp, name in pairs:
    for tag, root in (("CUR", DATA), ("BAK", BK)):
        p = root/mfp
        if not p.exists(): continue
        m = C.parse(p.read_bytes())
        for i,pk in enumerate(m["packs"]):
            if C.name_of(pk)!=name: continue
            segs = C.segments(m,i)
            encs = set()
            for bi,off,sz in segs:
                b = m["bundles"][bi]
                encs.add(b["encrypted"])
            tot = sum(s[2] for s in segs)
            print("%-32s %-4s %-11d %-10s %-4d %-6s 覆盖=%d/%d" % (name, tag, pk["size"], "%08x"%pk["crc"], len(segs), sorted(encs), tot, pk["size"]))
