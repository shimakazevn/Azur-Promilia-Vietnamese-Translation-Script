import sys, hashlib
from pathlib import Path
sys.path.insert(0,".")
import crcchain as C
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
B = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")
rel = ".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes"
a = C.parse((P/rel).read_bytes()); b = C.parse((B/rel).read_bytes())
na = {C.name_of(p): p for p in a["packs"]}; nb = {C.name_of(p): p for p in b["packs"]}
k = "3iffxeedh2grvnbn2iag.r"
print("原版  crc=%08x size=%d" % (nb[k]["crc"], nb[k]["size"]))
print("payload crc=%08x size=%d" % (na[k]["crc"], na[k]["size"]))
print("manifest 字节相同:", (P/rel).read_bytes() == (B/rel).read_bytes())
print("payload .hash:", (P/rel).with_suffix(".hash").read_text().strip())
print("md5(payload manifest):", hashlib.md5((P/rel).read_bytes()).hexdigest())
