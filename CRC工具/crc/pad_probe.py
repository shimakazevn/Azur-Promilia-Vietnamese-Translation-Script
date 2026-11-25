import sys
from pathlib import Path
sys.path.insert(0,".")
import crcchain as C
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
cases = [
 (".res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3221745.bytes", ".res/raw_streaming_package/BundleFiles", ["3iffxeedh2grvnbn2iag.r"]),
 (".res/raw_base_package/ManifestFiles/0release_raw_base_package_3221745.bytes", ".res/raw_base_package/BundleFiles", ["v0k2cafcxjxawklow6skg.r"]),
 (".res/default_package/ManifestFiles/0release_default_package_3221745.bytes", ".res/default_package/BundleFiles", ["owmxh3bjdhcwjoabqv67q.r"]),
 ("StreamingAssets/.res/default_package/0release_default_package_3060618.bytes", "StreamingAssets/.res/default_package", ["a66pm5ie1rrjguuzlsyq.r","p4hifvtlpthiunufa1lslg.r","db0aboccfhk0ruhzeueydq.r"]),
 ("StreamingAssets/.res/static_package/0release_static_package_3060618.bytes", "StreamingAssets/.res/static_package", ["nkewfips4anrz2bqfjhpg.r"]),
]
for mfp, bdir, names in cases:
    m = C.parse((E/mfp).read_bytes())
    idx = {}
    for i,pk in enumerate(m["packs"]):
        idx[C.name_of(pk)] = pk
    print("="*20, mfp.split("/")[-1])
    for n in names:
        pk = idx.get(n)
        if not pk: print("  ", n, "NOT FOUND"); continue
        pi = m["packs"].index(pk)
        segs = C.segments(m, pi)
        full = len(segs)==1 and segs[0][1]==0 and segs[0][2]==pk["size"]
        d = (E/bdir/n).read_bytes()
        tail = d[-16:]
        pad = 0
        for i in range(len(d)-1, len(d)-33, -1):
            if d[i]==0xAA: pad+=1
            else: break
        print("  %-34s size=%-10d segs=%-4d 单段覆盖全包=%-5s 尾部AA=%d bytes" % (n, pk["size"], len(segs), full, pad))
