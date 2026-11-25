# -*- coding: utf-8 -*-
import struct
from pathlib import Path

DATA = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
BK   = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\.zhcn-official-3221745-backup")

files = [
 ".res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r",
 ".res/raw_base_package/BundleFiles/v0k2cafcxjxawklow6skg.r",
 ".res/default_package/BundleFiles/owmxh3bjdhcwjoabqv67q.r",
 "StreamingAssets/.res/default_package/a66pm5ie1rrjguuzlsyq.r",
 "StreamingAssets/.res/default_package/p4hifvtlpthiunufa1lslg.r",
 "StreamingAssets/.res/default_package/db0aboccfhk0ruhzeueydq.r",
 "StreamingAssets/.res/static_package/nkewfips4anrz2bqfjhpg.r",
]
def cstr(b, p):
    e = b.index(b"\x00", p)
    return b[p:e].decode("utf-8","replace"), e+1
def rd(fmt, b, p):
    v = struct.unpack_from(fmt, b, p)
    return (v[0] if len(v)==1 else v), p + struct.calcsize(fmt)

for rel in files:
    name = rel.split("/")[-1]
    print("="*100)
    print(name)
    for tag, root in (("CUR", DATA), ("BAK", BK)):
        p = root/rel
        if not p.exists(): continue
        b = p.read_bytes()
        if b[:7] != b"UnityFS":
            print("  %-3s 非明文 UnityFS, 头16B=%s" % (tag, b[:16].hex(" ")))
            continue
        pos = 8
        ver, pos = rd(">I", b, pos)
        uv, pos = cstr(b, pos)
        rv, pos = cstr(b, pos)
        fsize, pos = rd(">q", b, pos)
        cib, pos = rd(">I", b, pos)
        uib, pos = rd(">I", b, pos)
        flags, pos = rd(">I", b, pos)
        alg = flags & 0x3f
        names = {0:"NONE",1:"LZMA",2:"LZ4",3:"LZ4HC"}
        print("  %-3s ver=%d uv=%-12s rv=%-14s fsize=%-10d real=%-10d cib=%-8d uib=%-8d flags=%08x alg=%s 头长=%d"
              % (tag, ver, uv, rv, fsize, len(b), cib, uib, flags, names.get(alg,alg), pos))
