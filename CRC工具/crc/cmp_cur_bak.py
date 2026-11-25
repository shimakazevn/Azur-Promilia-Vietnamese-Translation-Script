# -*- coding: utf-8 -*-
import sys, hashlib, zlib
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
import crcchain as C

DATA = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
BK   = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")

mfps = [
 ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes",
 ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes",
 ".res/default_package/ManifestFiles/0release_default_package_3221745.bytes",
 "StreamingAssets/.res/default_package/0release_default_package_3060618.bytes",
 "StreamingAssets/.res/static_package/0release_static_package_3060618.bytes",
]
watch = ["3iffxeedh2grvnbn2iag.r","v0k2cafcxjxawklow6skg.r","owmxh3bjdhcwjoabqv67q.r",
         "a66pm5ie1rrjguuzlsyq.r","p4hifvtlpthiunufa1lslg.r","db0aboccfhk0ruhzeueydq.r",
         "nkewfips4anrz2bqfjhpg.r"]
for mfp in mfps:
    print("="*90)
    print(mfp.split("/")[-1])
    for tag, root in (("CUR", DATA), ("BAK", BK)):
        p = root/mfp
        if not p.exists(): print("  %s 清单缺失"%tag); continue
        raw = p.read_bytes()
        hp = Path(str(p)+".hash")
        decl = hp.read_text().strip() if hp.exists() else None
        real = hashlib.md5(raw).hexdigest()
        print("  %s 清单 md5=%s  声明=%s  自洽=%s" % (tag, real[:10], (decl or "-")[:10], (decl or "").lower()==real))
        m = C.parse(raw)
        for n in watch:
            for i,pk in enumerate(m["packs"]):
                if C.name_of(pk)==n:
                    segs = C.segments(m,i)
                    # 找包文件位置
                    cand = [root/".res/raw_streaming_package/BundleFiles"/n,
                            root/".res/raw_base_package/BundleFiles"/n,
                            root/".res/default_package/BundleFiles"/n,
                            root/"StreamingAssets/.res/default_package"/n,
                            root/"StreamingAssets/.res/static_package"/n]
                    f = next((c for c in cand if c.exists()), None)
                    if f:
                        d = f.read_bytes()
                        ok = len(d)==pk["size"] and (zlib.crc32(d)&0xFFFFFFFF)==pk["crc"]
                        print("     %-32s 清单 size=%-10d crc=%08x | 实际 size=%-10d crc=%08x | 一致=%s | segs=%d"
                              % (n, pk["size"], pk["crc"], len(d), zlib.crc32(d)&0xFFFFFFFF, ok, len(segs)))
                    else:
                        print("     %-32s 清单 size=%-10d crc=%08x | 包文件缺失 | segs=%d" % (n, pk["size"], pk["crc"], len(segs)))
