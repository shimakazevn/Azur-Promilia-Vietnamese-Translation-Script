import sys, zlib, hashlib
from pathlib import Path
sys.path.insert(0, ".")
import crcchain as C

root = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data\StreamingAssets\.res\static_package")
mf = root/"0release_static_package_3060618.bytes"
pack = root/"3kuwgykc0rdjxcshnnjsq.r"
mb = mf.read_bytes()
print("verify before:", C.verify(mb, pack))

newp, newm, newh, rep = C.rebuild(mb, pack, {})
print("noop identical pack:", newp == pack.read_bytes())
print("noop identical manifest:", newm == mb)
print("noop hash:", newh.decode(), "==", hashlib.md5(mb).hexdigest())
print("verify(noop manifest, original pack):", C.verify(newm, pack))
