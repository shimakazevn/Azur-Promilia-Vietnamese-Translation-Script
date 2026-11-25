from pathlib import Path
P = Path(r"D:\windows\Desktop\蓝色星原简体汉化独立版\payload\tw_game")
E = Path(r"E:\AzurPromilia_TC\AzurPromilia_TC_game\AzurPromilia_Data")
files = [
 r".res/raw_streaming_package/BundleFiles/3iffxeedh2grvnbn2iag.r",
 r".res/raw_base_package/BundleFiles/v0k2cafcxjxawklow6skg.r",
 r"StreamingAssets/.res/static_package/nkewfips4anrz2bqfjhpg.r",
 r".res/default_package/BundleFiles/owmxh3bjdhcwjoabqv67q.r",
]
for rel in files:
    p = E/rel
    d = p.read_bytes()
    print("="*20, rel.split("/")[-1], "size", len(d))
    print("  head32", d[:32].hex(" "))
    print("  tail32", d[-32:].hex(" "))
    # 找 UnityFS 明文头（未加密时）
    for off in range(0, 256, 16):
        chunk = d[off:off+16]
        if b"UnityFS" in d[max(0,off-64):off+128]:
            print("  UnityFS 出现于附近:", off); break
