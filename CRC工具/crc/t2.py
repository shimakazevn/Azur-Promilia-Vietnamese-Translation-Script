import sys, zlib, hashlib, shutil
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

src = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\StreamingAssets\.res\static_package")
tmp = Path(r"C:\Users\xiaoxi\Documents\Codex\2026-11-25\ni\work\crc\sandbox")
tmp.mkdir(parents=True, exist_ok=True)
name = "lrqgmy8epzazxdzoxygvg.r"          # 17,812 字节的静态包
mf = src/"0release_static_package_3060618.bytes"
mb = mf.read_bytes()
m = C.parse(mb)
pi = [i for i,p in enumerate(m["packs"]) if C.name_of(p)==name][0]
segs = C.segments(m, pi)
print("pack", pi, name, "segments", segs)

orig = (src/name).read_bytes()
bi, off, size = segs[0]
seg = bytearray(orig[off:off+size])
print("bundle", bi, "size", size, "crc", hex(zlib.crc32(bytes(seg))))

# 只改 4 字节，模拟“替换文本后长度一致”的编辑
seg[1024:1028] = b"\xde\xad\xbe\xef"
newp, newm, newh, rep = C.rebuild(mb, src/name, {bi: bytes(seg)})
print("sizes", len(orig), len(newp), "| pack crc", hex(rep["oldPackCrc"]), "->", hex(rep["newPackCrc"]))
print("hash", newh.decode())

(tmp/"manifest.bytes").write_bytes(newm)
(tmp/name).write_bytes(newp)
print("re-verify:", C.verify(newm, tmp/name))

# 同时验证：若只改 pack 不改清单，会怎样
(tmp/"bad.r").write_bytes(newp)
m2 = C.parse(mb)
print("只改文件不改清单:", C.verify(mb, tmp/"bad.r"))
