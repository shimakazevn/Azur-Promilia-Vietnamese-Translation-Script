import sys, hashlib, zlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")

cases = [
 ("update/default",  P/".res/default_package/ManifestFiles/0release_default_package_3221745.bytes",
                     P/".res/default_package/BundleFiles",
                     E/".res/default_package/BundleFiles"),
 ("update/rawbase",  P/".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes",
                     P/".res/raw_base_package/BundleFiles",
                     E/".res/raw_base_package/BundleFiles"),
 ("update/rawstream",P/".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes",
                     P/".res/raw_streaming_package/BundleFiles",
                     E/".res/raw_streaming_package/BundleFiles"),
 ("builtin/default", P/"StreamingAssets/.res/default_package/0release_default_package_3060618.bytes",
                     P/"StreamingAssets/.res/default_package",
                     E/"StreamingAssets/.res/default_package"),
 ("builtin/static",  P/"StreamingAssets/.res/static_package/0release_static_package_3060618.bytes",
                     P/"StreamingAssets/.res/static_package",
                     E/"StreamingAssets/.res/static_package"),
]
for tag, mfp, pdir, origdir in cases:
    print("="*20, tag)
    if not mfp.exists():
        print("  manifest MISSING", mfp); continue
    mb = mfp.read_bytes()
    m = C.parse(mb)
    print("  manifest md5", hashlib.md5(mb).hexdigest())
    hp = mfp.with_suffix(".hash")
    if hp.exists():
        print("  .hash file  ", hp.read_text().strip(), "| match", hp.read_text().strip()==hashlib.md5(mb).hexdigest())
    else:
        print("  .hash file MISSING")
    # 对本包内每个 pack，检查 payload 里 / 原版里 哪个存在且自洽
    n_pay = n_orig = n_bad = 0
    bad = []
    for pk in m["packs"]:
        name = C.name_of(pk) + ".r"
        fp = pdir/name
        if fp.exists():
            d = fp.read_bytes()
            if len(d)==pk["size"] and (zlib.crc32(d)&0xFFFFFFFF)==pk["crc"]:
                n_pay += 1
            else:
                n_bad += 1
                if len(bad)<4: bad.append((name,"payload",len(d),pk["size"],hex(zlib.crc32(d)&0xFFFFFFFF),hex(pk["crc"])))
    print("  packs", len(m["packs"]), "| 在 payload 内自洽:", n_pay, "| 不自洽:", n_bad)
    for b in bad: print("     ", b)
