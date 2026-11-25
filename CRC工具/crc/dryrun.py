# -*- coding: utf-8 -*-
import sys, hashlib, zlib, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
import crcchain as C

E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
cases = [
 (".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes", ".res/raw_streaming_package/BundleFiles", ["3iffxeedh2grvnbn2iag.r"]),
 (".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes", ".res/raw_base_package/BundleFiles", ["v0k2cafcxjxawklow6skg.r"]),
 (".res/default_package/ManifestFiles/0release_default_package_3221745.bytes", ".res/default_package/BundleFiles", ["owmxh3bjdhcwjoabqv67q.r"]),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "StreamingAssets/.res/default_package", ["a66pm5ie1rrjguuzlsyq.r","p4hifvtlpthiunufa1lslg.r","db0aboccfhk0ruhzeueydq.r"]),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", "StreamingAssets/.res/static_package", ["nkewfips4anrz2bqfjhpg.r"]),
]
allok = True
for mfp, bdir, names in cases:
    mp = E/mfp
    mbytes = mp.read_bytes()
    hpath = Path(str(mp)+".hash")
    mhash_decl = hpath.read_text().strip() if hpath.exists() else "(none)"
    mhash_real = hashlib.md5(mbytes).hexdigest()
    print("="*70)
    print("MANIFEST", mp.name, "decl", mhash_decl[:12], "real", mhash_real[:12], "ok:", mhash_decl.lower()==mhash_real)
    m = C.parse(mbytes)
    for n in names:
        p = E/bdir/n
        old = p.read_bytes()
        idxs = [i for i,pk in enumerate(m["packs"]) if C.name_of(pk)==n]
        pk = m["packs"][idxs[0]]
        segs = C.segments(m, idxs[0])
        newp, newm, newhash, rep = C.rebuild(mbytes, p, {})
        ok = (newp==old) and (newm==mbytes) and rep["newPackSize"]==pk["size"] and rep["newPackCrc"]==pk["crc"]
        allok &= ok
        print("  %-32s segs=%-3d size=%-10d crc=%08x 原与清单一致=%-5s pack重建一致=%-5s 清单重建一致=%-5s"
              % (n, len(segs), pk["size"], pk["crc"], len(old)==pk["size"] and (zlib.crc32(old)&0xFFFFFFFF)==pk["crc"], newp==old, newm==mbytes))
print("="*70)
print("空跑总判定:", "全部通过" if allok else "有失败项")
