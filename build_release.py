"""校验替换资源并构建独立发行包。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
PACKAGE = "蓝色星原简体汉化独立版"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def payload_files(plan: dict, payload: Path):
    base = payload.resolve(strict=True)
    for item in [*plan["games"], *plan["launchers"]]:
        for entry in item.get("files", [item]):
            relative = PurePosixPath(item["payload_dir"], entry["relative_path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Invalid payload path: {relative}")
            path = base.joinpath(*relative.parts).resolve(strict=True)
            if not path.is_relative_to(base) or not path.is_file():
                raise ValueError(f"Invalid payload file: {relative}")
            if sha256(path) != entry["target_sha256"]:
                raise ValueError(f"SHA-256 mismatch: {relative}")
            yield path, f"payload/{relative.as_posix()}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True,
                        help="payload directory from the complete release package")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", default="v2", help="GitHub release tag, independent of payload patch_revision")
    args = parser.parse_args()
    plan = json.loads((ROOT / "tools/deployment-plan.json").read_text("utf-8-sig"))
    version = args.version
    if not version or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in version):
        raise ValueError("Invalid release version")
    files = list(payload_files(plan, args.payload))
    replacement_count = len(files)
    for relative in ("双击运行-汉化-还原.bat", "使用说明.txt",
                     "tools/Apply-OfficialZH.ps1", "tools/deployment-plan.json"):
        source = ROOT / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        files.append((source, relative))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"AzurPromilia-Localization-Full-{version}.zip"
    with ZipFile(archive, "x", ZIP_DEFLATED, compresslevel=6) as package:
        for source, relative in sorted(files, key=lambda item: item[1]):
            package.write(source, f"{PACKAGE}/{relative}")
    with ZipFile(archive) as package:
        damaged = package.testzip()
        if damaged:
            raise ValueError(f"Archive verification failed: {damaged}")
    digest = sha256(archive)
    checksums = output / "SHA256SUMS.txt"
    checksums.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"{archive}\n{digest}\nVerified replacement files: {replacement_count}")


if __name__ == "__main__":
    main()
