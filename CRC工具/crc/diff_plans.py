import sys, hashlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
pairs = [
 (".res/default_package/ManifestFiles/0release_default_package_3221745.bytes",
  ".res/default_package/ManifestFiles/0release_default_package_3221745.bytes", "owmxh3bjdhcwjoabqv67q"),
 (".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes",
  ".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes", "v0k2cafcxjxawklow6skg"),
 (".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes",
  ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes", "3iffxeedh2grvnbn2iag"),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes",
  "StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", None),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes",
  "StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", "nkewfips4anrz2bqfjhpg"),
]
for rel, rel2, target in pairs:
    a = C.parse((P/rel).read_bytes())
    b = C.parse((E/rel2).read_bytes())
    print("="*18, rel.split("/")[-1])
    print("   payload md5", hashlib.md5((P/rel).read_bytes()).hexdigest()[:16], "| 原版 md5", hashlib.md5((E/rel2).read_bytes()).hexdigest()[:16],
          "| 不同" if (P/rel).read_bytes()!= (E/rel2).read_bytes() else "| 相同")
    if target:
        na = {C.name_of(pk): pk for pk in a["packs"]}
        nb = {C.name_of(pk): pk for pk in b["packs"]}
        pa = na.get(target + ".r"); pb = nb.get(target + ".r")
        if pa and pb:
            print("   pack crc  payload %08x / 原版 %08x  %s" % (pa["crc"], pb["crc"], "已更新" if pa["crc"]!=pb["crc"] else "未变"))
        else:
            print("   pack 未找到", bool(pa), bool(pb))
    else:
        changed = sum(1 for x,y in zip(a["packs"], b["packs"]) if (x["crc"],x["size"])!=(y["crc"],y["size"]))
        print("   packs", len(a["packs"]), "| crc/size 变化条数", changed)
        print("   首个变化:", [(i, hex(x["crc"]), hex(y["crc"])) for i,(x,y) in enumerate(zip(a["packs"],b["packs"])) if x["crc"]!=y["crc"]][:4])
