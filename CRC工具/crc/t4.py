import sys, zlib, hashlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

src = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\StreamingAssets\.res\static_package")
mf  = src/"0release_static_package_3060618.bytes"
mb  = mf.read_bytes()
m   = C.parse(mb)

# 找一个多 bundle 共享的包更好；static 每个包只有 1 段，先用 default 包里的多段 pack
# 这里改用内存方式模拟“变长”替换：给 segment 追加 37 字节
name = "lrqgmy8epzazxdzoxygvg.r"
pi   = [i for i,p in enumerate(m["packs"]) if C.name_of(p)==name][0]
segs = C.segments(m, pi)
bi, off, size = segs[0]
orig = (src/name).read_bytes()
seg  = orig[off:off+size] + b"\x00"*37     # 变长 +37

newp, newm, newh, rep = C.rebuild(mb, src/name, {bi: seg})
print("len", len(orig), "->", len(newp))
print("pack crc", hex(rep["oldPackCrc"]), "->", hex(rep["newPackCrc"]))
print("hash", newh.decode())

# 纯内存复验：用新清单核对新 pack
m2 = C.parse(newm)
errs = []
pk = m2["packs"][pi]
if pk["size"] != len(newp): errs.append("pack size")
if (zlib.crc32(newp)&0xFFFFFFFF) != pk["crc"]: errs.append("pack crc")
for bj, o2, s2 in C.segments(m2, pi):
    b = m2["bundles"][bj]
    s = newp[b["offset"]:b["offset"]+b["size"]]
    if len(s) != b["size"]: errs.append("bundle %d size"%bj)
    elif (zlib.crc32(s)&0xFFFFFFFF) != b["crc"]: errs.append("bundle %d crc"%bj)
print("in-memory re-verify:", errs or "OK")
print("md5(new manifest)==hash:", hashlib.md5(newm).hexdigest().encode()==newh)
print("hashes[] untouched:", C.parse(newm)["hashes"]==C.parse(mb)["hashes"])
