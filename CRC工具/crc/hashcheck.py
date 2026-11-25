# -*- coding: utf-8 -*-
import sys, hashlib
from pathlib import Path
sys.path.insert(0, r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
mfps = [
 ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes",
 ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes",
 ".res/default_package/ManifestFiles/0release_default_package_3221745.bytes",
 "StreamingAssets/.res/default_package/0release_default_package_3060618.bytes",
 "StreamingAssets/.res/static_package/0release_static_package_3060618.bytes",
]
for m in mfps:
    p = E/m
    b = p.read_bytes()
    real = hashlib.md5(b).hexdigest()
    for cand in [Path(str(p)+".hash"), p.with_suffix(".hash"), Path(str(p)[:-6]+".hash")]:
        if cand.exists():
            decl = cand.read_text().strip()
            print("%-22s hash文件=%-52s decl=%s real=%s ok=%s" % (p.name[:22], cand.name, decl[:10], real[:10], decl.lower()==real))
            break
    else:
        print(p.name, "NO HASH FILE")
