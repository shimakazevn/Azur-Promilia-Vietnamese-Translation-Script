import sys, hashlib
from pathlib import Path
sys.path.insert(0,".")
import crcchain as C
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
B = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")
cases = [
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", ["a66pm5ie1rrjguuzlsyq.r","p4hifvtlpthiunufa1lslg.r","db0aboccfhk0ruhzeueydq.r"]),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", ["nkewfips4anrz2bqfjhpg.r"]),
]
for rel, names in cases:
    pm = P/rel; bm = B/rel
    pa = C.parse(pm.read_bytes()); ba = C.parse(bm.read_bytes())
    print("="*18, rel.split("/")[-1])
    print("   payload manifest md5", hashlib.md5(pm.read_bytes()).hexdigest()[:16],
          "| 原版(backup) md5", hashlib.md5(bm.read_bytes()).hexdigest()[:16] if bm.exists() else "MISSING")
    print("   字节相同:", pm.read_bytes()==bm.read_bytes() if bm.exists() else "n/a")
    na = {C.name_of(x):x for x in pa["packs"]}
    nb = {C.name_of(x):x for x in ba["packs"]} if bm.exists() else {}
    for n in names:
        a=na.get(n); b=nb.get(n)
        if a and b:
            print("   %-32s payload size=%9d crc=%08x | 原版 size=%9d crc=%08x | %s" % (
                n, a["size"], a["crc"], b["size"], b["crc"], "已更新" if (a["crc"],a["size"])!=(b["crc"],b["size"]) else "未变"))
        else:
            print("   %-32s payload=%s backup=%s" % (n, bool(a), bool(b)))
