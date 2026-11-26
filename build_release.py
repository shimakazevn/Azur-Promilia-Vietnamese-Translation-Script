"""校验替换资源并构建完整包与源码包。"""
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
PACKAGES = {'zhcn': '蓝色星原简体汉化', 'vi': 'Azur Promilia Vietnamese Localization', 'en': 'Azur Promilia English Localization'}


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
    parser.add_argument('--language', default='zhcn', choices=['zhcn', 'vi', 'en'], help='Target language; vi/en need a real payload first')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]+', args.version):
        raise ValueError('版本名称无效')
    catalog_name = 'tools/package-files.json' if args.language == 'zhcn' else f"tools/package-files-{args.language}.json"
    catalog = json.loads((ROOT / catalog_name).read_text('utf-8-sig'))
    if catalog.get('status') == 'placeholder-no-payload':
        raise ValueError(f'payload catalog for {args.language} is a placeholder: no payload files exist yet')
    if catalog['format'] != 1 or catalog['hash'] != 'SHA256':
        raise ValueError('文件清单格式无效')
    payload_prefix = 'payload/' if args.language == 'zhcn' else f'payload-{args.language}/'
    entries = {}
    for item in catalog['files']:
        relative = item['path']
        if relative in entries:
            raise ValueError(f'重复包内路径：{relative}')
        source = child(args.payload, relative[len(payload_prefix):]) if relative.startswith(payload_prefix) else child(ROOT, relative)
        if source.stat().st_size != item['size'] or sha256(source) != item['sha256']:
            raise ValueError(f'文件校验失败：{relative}')
        entries[relative] = source
    for name in (catalog_name, 'tools/安装路径.json', 'tools/language.json'):
        entries[name] = child(ROOT, name)
    setup_exe = ROOT / 'dist' / 'AzurPromilia-VI-Setup.exe'
    if args.language == 'vi' and setup_exe.is_file():
        entries['AzurPromilia-VI-Setup.exe'] = setup_exe
        entries['VERSION.txt'] = None
    source_names = ['.gitignore', 'LICENSE', 'README.md', 'build_release.py', '双击运行.bat']
    if (ROOT / 'CaiDat-Android-ADB.bat').is_file():
        source_names.append('CaiDat-Android-ADB.bat')
    if (ROOT / '使用说明.txt').is_file():
        source_names.append('使用说明.txt')
    if (ROOT / 'latest-vi.json').is_file():
        source_names.append('latest-vi.json')
    source_names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'tools').iterdir()) if p.is_file()]
    if (ROOT / 'installer').is_dir():
        source_names += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / 'installer').rglob('*')) if p.is_file()]
    if (ROOT / 'android-installer').is_dir():
        source_names += [
            p.relative_to(ROOT).as_posix()
            for p in sorted((ROOT / 'android-installer').rglob('*'))
            if p.is_file()
            and not any(part in ('build', '.gradle') for part in p.relative_to(ROOT).parts)
            and p.suffix not in ('.jks', '.keystore', '.apk')
            and p.name != 'local.properties'
        ]
    sources = [(child(ROOT, name), name) for name in source_names]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    full = output / f'AzurPromilia-Localization-Full-{args.language}-{args.version}.zip'
    source = output / f'AzurPromilia-Localization-Source-{args.language}-{args.version}.zip'
    for path in (full, source):
        if path.exists():
            path.unlink()
    package = PACKAGES[args.language]
    ver_tmp = None
    if 'VERSION.txt' in entries and entries['VERSION.txt'] is None:
        ver_tmp = output / '.VERSION.tmp'
        ver_tmp.write_text(args.version + '\n', encoding='utf-8')
        entries['VERSION.txt'] = ver_tmp
    try:
        archive(full, [(path, name) for name, path in sorted(entries.items())], package)
    finally:
        if ver_tmp is not None and ver_tmp.exists():
            ver_tmp.unlink()
    archive(source, sources, package + '-源码')
    sums_items = [full, source]
    if args.language == 'vi' and setup_exe.is_file():
        sums_items.append(setup_exe)
    checksums = ''.join(f'{sha256(path)}  {path.name}\n' for path in sums_items)
    (output / 'SHA256SUMS.txt').write_text(checksums, 'ascii')
    if args.language == 'vi':
        from datetime import datetime, timezone
        import shutil
        repo_slug = 'shimakazevn/Azur-Promilia-Vietnamese-Translation-Script'
        base_dl = f'https://github.com/{repo_slug}/releases/download/{args.version}'

        android_obj = None
        android_plan_path = ROOT / 'tools' / 'android-deployment-vi.json'
        android_payload_dir = ROOT / 'payload-vi' / 'android_game'
        if android_plan_path.is_file() and android_payload_dir.is_dir():
            android_plan = json.loads(android_plan_path.read_text('utf-8-sig'))
            az_entries = []
            for item in android_plan['files']:
                rel = item['relative_path']
                p = child(android_payload_dir, rel)
                if p.stat().st_size != item['size'] or sha256(p) != item['target_sha256']:
                    raise ValueError(f'Android payload verify failed: {rel}')
                az_entries.append((p, f'android_game/{rel}'))
            az_entries.append((android_plan_path, 'tools/android-deployment-vi.json'))
            if (ROOT / 'tools' / 'Apply-AndroidVI.ps1').is_file():
                az_entries.append((ROOT / 'tools' / 'Apply-AndroidVI.ps1', 'tools/Apply-AndroidVI.ps1'))
            if (ROOT / 'CaiDat-Android-ADB.bat').is_file():
                az_entries.append((ROOT / 'CaiDat-Android-ADB.bat', 'CaiDat-Android-ADB.bat'))

            az_zip = output / f'AzurPromilia-Localization-Android-vi-{args.version}.zip'
            if az_zip.exists():
                az_zip.unlink()
            archive(az_zip, az_entries, 'AzurPromilia-VI-Android')
            sums_items.append(az_zip)

            apk_src = ROOT / 'android-installer' / 'app' / 'build' / 'outputs' / 'apk' / 'release' / 'app-release.apk'
            apk_dist = output / 'AzurPromilia-VI-Mobile.apk'
            apk_info = None
            if apk_src.is_file():
                shutil.copy2(apk_src, apk_dist)
                sums_items.append(apk_dist)
                apk_info = {
                    'version': args.version,
                    'filename': apk_dist.name,
                    'size': apk_dist.stat().st_size,
                    'sha256': sha256(apk_dist),
                    'url': f'{base_dl}/{apk_dist.name}',
                }
            elif apk_dist.is_file():
                sums_items.append(apk_dist)
                apk_info = {
                    'version': args.version,
                    'filename': apk_dist.name,
                    'size': apk_dist.stat().st_size,
                    'sha256': sha256(apk_dist),
                    'url': f'{base_dl}/{apk_dist.name}',
                }

            android_obj = {
                'package_name': android_plan.get('package_name', 'com.Yostar.AzurpromiliaJP'),
                'resource_version': android_plan.get('resource_version', '3219596'),
                'filename': az_zip.name,
                'size': az_zip.stat().st_size,
                'sha256': sha256(az_zip),
                'url': f'{base_dl}/{az_zip.name}',
            }
            if apk_info:
                android_obj['apk'] = apk_info

        checksums = ''.join(f'{sha256(path)}  {path.name}\n' for path in sums_items)
        (output / 'SHA256SUMS.txt').write_text(checksums, 'ascii')

        latest = {
            'schema_version': 1,
            'language': 'vi',
            'version': args.version,
            'published_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'repo': repo_slug,
            'jp_resource_version': '3219598',
            'jp_builtin_version': '3075915',
            'jp_launcher_version': '1.8.1',
            'full_package': {
                'filename': full.name,
                'size': full.stat().st_size,
                'sha256': sha256(full),
                'url': f'{base_dl}/{full.name}',
            },
            'installer': {
                'filename': setup_exe.name if setup_exe.is_file() else 'AzurPromilia-VI-Setup.exe',
                'size': setup_exe.stat().st_size if setup_exe.is_file() else 0,
                'sha256': sha256(setup_exe) if setup_exe.is_file() else '',
                'url': f'{base_dl}/AzurPromilia-VI-Setup.exe',
            },
            'notes': f'{args.version}: Hoàn thiện UI chuẩn Genshin-RPG gọn nhẹ (Túi, Đội, Du Ký, Sổ Tay, Vọng Tinh, Trang Viên, Break, Shield, Bạo Kích), sửa lỗi dịch máy & đảo ngữ Hán-Việt. Hỗ trợ cả PC (3219598) và Android Shizuku/ADB (3219596).',
        }
        if android_obj:
            latest['android'] = android_obj
        latest_txt = json.dumps(latest, indent=2, ensure_ascii=False) + '\n'
        (ROOT / 'latest-vi.json').write_text(latest_txt, encoding='utf-8')
        (output / 'latest-vi.json').write_text(latest_txt, encoding='utf-8')
    print(json.dumps({'archives': [str(full), str(source)], 'package_files': len(entries),
                      'replacement_files': sum(name.startswith(payload_prefix) for name in entries),
                      'language': args.language,
                      'source_files': len(sources)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
