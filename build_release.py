"""校验替换资源并构建完整包与源码包。"""
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
PACKAGE = '蓝色星原简体汉化'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def child(root, relative):
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative) or ':' in str(relative):
        raise ValueError(f'包内路径无效：{relative}')
    root = root.resolve(strict=True)
    path = root.joinpath(*relative.parts).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f'文件路径无效：{relative}')
    return path


def archive(path, entries, prefix):
    with ZipFile(path, 'x', ZIP_DEFLATED, compresslevel=6) as package:
        for source, relative in entries:
            package.write(source, f'{prefix}/{relative}')
    with ZipFile(path) as package:
        damaged = package.testzip()
        if damaged:
            raise ValueError(f'压缩包校验失败：{damaged}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True, help='完整包中的 payload 文件夹')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--version', default='v3')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]+', args.version):
        raise ValueError('版本名称无效')
    catalog = json.loads((ROOT / 'tools/package-files.json').read_text('utf-8-sig'))
    if catalog['format'] != 1 or catalog['hash'] != 'SHA256':
        raise ValueError('文件清单格式无效')
    entries = {}
    for item in catalog['files']:
        relative = item['path']
        if relative in entries:
            raise ValueError(f'重复包内路径：{relative}')
        source = child(args.payload, relative[8:]) if relative.startswith('payload/') else child(ROOT, relative)
        if source.stat().st_size != item['size'] or sha256(source) != item['sha256']:
            raise ValueError(f'文件校验失败：{relative}')
        entries[relative] = source
    for name in ('tools/package-files.json', 'tools/安装路径.json'):
        entries[name] = child(ROOT, name)
    source_names = ['.gitignore', 'LICENSE', 'README.md', 'build_release.py', '使用说明.txt', '双击运行.bat']
    source_names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'tools').iterdir()) if p.is_file()]
    sources = [(child(ROOT, name), name) for name in source_names]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    full = output / f'AzurPromilia-Localization-Full-{args.version}.zip'
    source = output / f'AzurPromilia-Localization-Source-{args.version}.zip'
    for path in (full, source):
        if path.exists():
            raise FileExistsError(path)
    archive(full, [(path, name) for name, path in sorted(entries.items())], PACKAGE)
    archive(source, sources, PACKAGE + '-源码')
    checksums = ''.join(f'{sha256(path)}  {path.name}\n' for path in (full, source))
    (output / 'SHA256SUMS.txt').write_text(checksums, 'ascii')
    print(json.dumps({'archives': [str(full), str(source)], 'package_files': len(entries),
                      'replacement_files': sum(name.startswith('payload/') for name in entries),
                      'source_files': len(sources)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
