import hashlib, zlib
from pathlib import Path
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
B = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")
files = [
 (".res/default_package/BundleFiles/owmxh3bjdhcwjoabqv67q.r",)*1,
 (".res/raw_base_package/BundleFiles/v0k2cafcxjxawklow6skg.r",),
 (".res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r",),
 ("StreamingAssets/.res/default_package/a66pm5ie1rrjguuzlsyq.r",),
 ("StreamingAssets/.res/default_package/p4hifvtlpthiunufa1lslg.r",),
 ("StreamingAssets/.res/default_package/db0aboccfhk0ruhzeueydq.r",),
 ("StreamingAssets/.res/static_package/nkewfips4anrz2bqfjhpg.r",),
]
for (rel,) in files:
    row = [rel.split("/")[-1]]
    for tag, root in [("payload",P),("install",E),("backup",B)]:
        f = root/rel
        if f.exists():
            d = f.read_bytes()
            row.append("%s:%d/%s" % (tag, len(d), hashlib.sha256(d).hexdigest()[:10]))
        else:
            row.append(tag+":-")
    print("  ".join(row))
