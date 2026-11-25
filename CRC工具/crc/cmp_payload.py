# -*- coding: utf-8 -*-
import sys, hashlib, struct
from pathlib import Path
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
D = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
rels = [
 (".res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r",),
 (".res/raw_base_package/BundleFiles/v0k2cafcxjxawklow6skg.r",),
 (".res/default_package/BundleFiles/owmxh3bjdhcwjoabqv67q.r",),
 ("StreamingAssets/.res/default_package/a66pm5ie1rrjguuzlsyq.r",),
 ("StreamingAssets/.res/default_package/p4hifvtlpthiunufa1lslg.r",),
 ("StreamingAssets/.res/default_package/db0aboccfhk0ruhzeueydq.r",),
 ("StreamingAssets/.res/static_package/nkewfips4anrz2bqfjhpg.r",),
]
for (rel,) in rels:
    a = E/rel
    b = D/rel
    ha = hashlib.md5(a.read_bytes()).hexdigest() if a.exists() else None
    hb = hashlib.md5(b.read_bytes()).hexdigest() if b.exists() else None
    sa = a.stat().st_size if a.exists() else -1
    sb = b.stat().st_size if b.exists() else -1
    ta = a.stat().st_mtime if a.exists() else 0
    import datetime
    print("%-32s E=%d(%s) D=%d(%s) 相同=%s  E时间=%s" % (
        rel.split("/")[-1], sa, (ha or "")[:8], sb, (hb or "")[:8], ha==hb,
        datetime.datetime.fromtimestamp(ta).strftime("%Y-%m-%d %H:%M") if ta else "-"))
    # 头部识别
    if a.exists():
        d = a.read_bytes()[:64]
        print("      head:", d[:32].hex(" "))
        if d[:5]==b"UnityFS":
            print("      -> 明文 UnityFS")
        else:
            print("      首4字节:", d[:4].hex(" "), " 8-12:", d[8:12].hex(" "))
