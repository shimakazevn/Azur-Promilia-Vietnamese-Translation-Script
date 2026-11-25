# -*- coding: utf-8 -*-
import sys, hashlib
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
import crcchain as C

DATA = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
BK   = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")
rels = [
 ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes",
 ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes",
 ".res/default_package/ManifestFiles/0release_default_package_3221745.bytes",
 "StreamingAssets/.res/default_package/0release_default_package_3060618.bytes",
 "StreamingAssets/.res/static_package/0release_static_package_3060618.bytes",
]
for rel in rels:
    a = DATA/rel; b = BK/rel
    print("="*78)
    print(rel.split("/")[-1], " 当前", a.stat().st_size if a.exists() else None, " 备份", b.stat().st_size if b.exists() else None)
    for tag,p in (("CUR",a),("BAK",b)):
        if not p.exists(): print("  ",tag,"缺"); continue
        raw = p.read_bytes()
        try:
            m = C.parse(raw)
            print("  %s packs=%d bundles=%d assets=%d md5=%s" % (tag, len(m["packs"]), len(m["bundles"]), len(m["assets"]), hashlib.md5(raw).hexdigest()[:10]))
            for pk in m["packs"]:
                print("      pack %-32s size=%-10d crc=%08x uid=%d" % (C.name_of(pk), pk["size"], pk["crc"], pk["uid"]))
        except Exception as e:
            print("  %s 解析失败: %r" % (tag, e))
