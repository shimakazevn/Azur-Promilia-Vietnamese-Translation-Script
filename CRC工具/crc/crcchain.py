# -*- coding: utf-8 -*-
"""YooAsset 2.3.1 定制清单 CRC 链重算工具（只操作副本，不碰安装目录）。

结构事实（已由 parse_manifest.py + 全量实测确认）：
  manifest = 4F4F5900 + 3 strings + pipeline/package/version/buildTime
             + assets[6i] + assetDependPool[int]
             + bundles[56B: size(q) crc(I) nameIndex(i) dependCount(i)
                              refOffset(i) refCount(i) assetCount(i) packId(i)
                              offset(q) tags(I) index(i) encrypt(B) refCount(B) r1(B) r2(B)]
             + bundleReferencePool[int]
             + hashes[n x (QQ)]   # bundle 的 hash 文件名（base38 两段）
             + packs[48B: name0(Q) name1(Q) hash0(Q) hash1(Q) size(q) uid(I) crc(I)]

校验关系（全部实测 100% 成立）：
  pack.crc   == zlib.crc32(整个 .r 文件)
  pack.size  == 文件长度
  bundle.crc == zlib.crc32(pack文件[offset:offset+size])
  bundle.size== 段长度
  <manifest>.hash 文件内容 == md5(manifest bytes) 的小写 hex（32 字节 ASCII）
  客户端验证：ManifestTools.VerifyManifestData(data, hashValue)
      if len(hashValue) != 0x20 -> BytesCRC32
      else                      -> BytesMD5   (忽略大小写字符串比较)
  单文件验证：FileVerifyHelper.VerifyFile(path,size,crc,level)
      size 不等 -> FileNotComplete / FileOverflow
      level==3(High) -> 再比 CRC32 -> FileCrcError
      level 1(Low)/2(Middle) -> 只比 size
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

MAGIC = 0x594F4F
ALPHA = " 0123456789abcdefghijklmnopqrstuvwxyz."


def b38(n):
    if n == 0:
        return ""
    s = ""
    while n:
        n, d = divmod(n, 38)
        s = ALPHA[d] + s
    return s


def name_of(pack):
    return b38(pack["name0"]) + b38(pack["name1"])


def find_pack(m, pack_path):
    p = Path(pack_path)
    base = p.name
    stem = p.stem
    idx = [i for i, pk in enumerate(m["packs"]) if name_of(pk) in (base, stem)]
    if len(idx) != 1:
        raise ValueError("manifest 中找不到唯一的 pack: %s (命中 %d)" % (base, len(idx)))
    return idx[0], m["packs"][idx[0]]


class Reader:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def get(self, fmt):
        v = struct.unpack_from("<" + fmt, self.b, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def string(self):
        n = self.get("H")
        v = self.b[self.p:self.p + n].decode("utf-8", "replace")
        self.p += n
        return v

    def array(self, fmt):
        n = self.get("i")
        return [self.get(fmt) for _ in range(n)]


def parse(path):
    raw = path if isinstance(path, (bytes, bytearray)) else Path(path).read_bytes()
    r = Reader(raw)
    assert r.get("I") == MAGIC, "not a YooAsset manifest"
    out = {"format": r.string(), "flags": r.get("3B"),
           "name_style": r.get("i"), "bundle_type": r.get("i")}
    out["pipeline"], out["package"], out["version"], out["note"] = [r.string() for _ in range(4)]
    out["asset_count_offset"] = r.p
    out["assets"] = [dict(zip(["bundle", "pathKey", "dependStart", "dependCount", "tags", "index"], v))
                     for v in r.array("6i")]
    out["asset_depend_pool"] = r.array("i")
    out["bundle_count_offset"] = r.p
    out["bundles"] = [dict(zip(["size", "crc", "nameIndex", "dependCount", "refOffset",
                                "refCount", "assetCount", "packId", "offset", "tags",
                                "index", "encrypted", "refCountB", "r1", "r2"], v))
                      for v in r.array("qIiiiiiiqIi4B")]
    out["bundle_reference_pool"] = r.array("i")
    out["hashes"] = [r.get("QQ") for _ in range(r.get("i"))]
    out["pack_count_offset"] = r.p
    out["packs"] = [dict(zip(["name0", "name1", "hash0", "hash1", "size", "uid", "crc"], v))
                    for v in r.array("QQQQqII")]
    assert r.p == len(raw), ("trailing bytes", r.p, len(raw))
    return out


def segments(m, pack_index, pack_bytes_len=None):
    """返回该 pack 内的 bundle 段 [(bundle_index, offset, size)]，按 offset 排序。"""
    return sorted(((i, b["offset"], b["size"]) for i, b in enumerate(m["bundles"])
                   if b["packId"] == pack_index), key=lambda x: x[1])


def rebuild(manifest_bytes, pack_path, replacements):
    """把 replacements{bundle_index: bytes} 写进 pack 文件，并返回
    (new_pack_bytes, new_manifest_bytes, new_hash_ascii, report)。

    变长替换会重排后续 bundle 的 offset，并同步 size/crc。
    """
    m = parse(manifest_bytes)
    pack_path = Path(pack_path)
    base = pack_path.name
    pi, pk = find_pack(m, pack_path)
    old = pack_path.read_bytes()
    if len(old) != pk["size"] or (zlib.crc32(old) & 0xFFFFFFFF) != pk["crc"]:
        raise ValueError("原 pack 与清单不符，先确认文件未被改过")

    segs = segments(m, pi)
    mv = memoryview(old)
    for bi, _, _ in segs:
        b = m["bundles"][bi]
        seg = mv[b["offset"]:b["offset"] + b["size"]]
        if (zlib.crc32(seg) & 0xFFFFFFFF) != b["crc"]:
            raise ValueError("原 bundle 段 %d CRC 与清单不符" % bi)

    seg_ids = {s[0] for s in segs}
    for bi in replacements:
        if bi not in seg_ids:
            raise ValueError("bundle %d 不属于该 pack" % bi)

    out = bytearray()
    cursor = 0
    manifest = bytearray(manifest_bytes)
    changes = []
    for bi, off, size in segs:
        out.extend(old[cursor:off])
        newoff = len(out)
        seg = replacements.get(bi, old[off:off + size])
        out.extend(seg)
        bpos = m["bundle_count_offset"] + 4 + bi * 56
        struct.pack_into("<qI", manifest, bpos, len(seg), zlib.crc32(seg) & 0xFFFFFFFF)
        struct.pack_into("<q", manifest, bpos + 36, newoff)
        if bi in replacements:
            changes.append(dict(bundle=bi, oldSize=size, newSize=len(seg),
                                oldOffset=off, newOffset=newoff))
        cursor = off + size
    out.extend(old[cursor:])
    new_pack = bytes(out)

    ppos = m["pack_count_offset"] + 4 + pi * 48
    struct.pack_into("<q", manifest, ppos + 32, len(new_pack))
    struct.pack_into("<I", manifest, ppos + 44, zlib.crc32(new_pack) & 0xFFFFFFFF)
    new_manifest = bytes(manifest)
    new_hash = hashlib.md5(new_manifest).hexdigest().encode("ascii")
    return new_pack, new_manifest, new_hash, dict(
        packIndex=pi, packName=base, oldPackSize=len(old), newPackSize=len(new_pack),
        oldPackCrc=zlib.crc32(old) & 0xFFFFFFFF,
        newPackCrc=zlib.crc32(new_pack) & 0xFFFFFFFF,
        changes=changes)


def verify(manifest_bytes, pack_path):
    """全量回验一个 pack：段 CRC、段 size、pack CRC、pack size。"""
    m = parse(manifest_bytes)
    data = Path(pack_path).read_bytes()
    pi, pk = find_pack(m, pack_path)
    errs = []
    if len(data) != pk["size"]:
        errs.append("pack size %d != %d" % (len(data), pk["size"]))
    if (zlib.crc32(data) & 0xFFFFFFFF) != pk["crc"]:
        errs.append("pack crc mismatch")
    mv = memoryview(data)
    for bi, off, size in segments(m, pi):
        b = m["bundles"][bi]
        seg = mv[b["offset"]:b["offset"] + b["size"]]
        if len(seg) != b["size"]:
            errs.append("bundle %d size" % bi)
        elif (zlib.crc32(seg) & 0xFFFFFFFF) != b["crc"]:
            errs.append("bundle %d crc" % bi)
    return errs


def main():
    parser = argparse.ArgumentParser(description="YooAsset 清单解析与包校验")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_insp = sub.add_parser("inspect", help="查看 manifest 摘要")
    p_insp.add_argument("manifest", type=Path)
    p_ver = sub.add_parser("verify", help="校验 .r 包与 manifest 是否匹配")
    p_ver.add_argument("manifest", type=Path)
    p_ver.add_argument("pack", type=Path)
    args = parser.parse_args()

    if args.cmd == "inspect":
        m = parse(args.manifest)
        print(json.dumps({
            "package": m["package"],
            "version": m["version"],
            "assets": len(m["assets"]),
            "bundles": len(m["bundles"]),
            "packs": len(m["packs"]),
        }, ensure_ascii=False, indent=2))
    elif args.cmd == "verify":
        errs = verify(args.manifest.read_bytes(), args.pack)
        print(json.dumps({"ok": not errs, "errors": errs}, ensure_ascii=False))
        raise SystemExit(0 if not errs else 1)


if __name__ == "__main__":
    main()
