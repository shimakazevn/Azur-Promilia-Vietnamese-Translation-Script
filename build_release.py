"""校验替换资源、刷新清单并构建完整包、Android包与源码包 (支持 --language zhcn|vi|en)。"""
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
import argparse
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parent

PACKAGES = {
    'zhcn': '蓝色星原简体汉化',
    'vi': 'AzurPromilia-VietHoa',
    'en': 'AzurPromilia-Localization-EN',
}

CORE_NON_PAYLOAD_PATHS = [
    'tools/Apply-CRCZH.ps1',
    'tools/Apply-JPCRCZH.ps1',
    'tools/Apply-JPDeblur.ps1',
    'tools/Apply-TWDeblur.ps1',
    'tools/tw-deblur-deployment.json',
    'tools/jp-deblur-deployment.json',
    'tools/Apply-Launchers.ps1',
    'tools/Localization-Common.ps1',
    'tools/jp-deployment.json',
    'tools/launcher-deployment.json',
    'tools/Locate-Installations.ps1',
    'tools/Manage-Localization.ps1',
    'tools/tw-deployment.json',
    '使用说明.txt',
    '双击运行.bat',
]

VI_CORE_NON_PAYLOAD_PATHS = [
    'tools/Apply-CRCZH.ps1',
    'tools/Apply-JPCRCZH.ps1',
    'tools/Apply-JPDeblur.ps1',
    'tools/Apply-TWDeblur.ps1',
    'tools/tw-deblur-deployment.json',
    'tools/jp-deblur-deployment.json',
    'tools/Apply-Launchers.ps1',
    'tools/Localization-Common.ps1',
    'tools/jp-deployment-vi.json',
    'tools/launcher-deployment-vi.json',
    'tools/Locate-Installations.ps1',
    'tools/Manage-Localization.ps1',
    'tools/tw-deployment-vi.json',
    'tools/language.json',
    '使用说明.txt',
    '双击运行.bat',
]

SOURCE_SUFFIXES = {
    '.py', '.ps1', '.json', '.md', '.txt', '.bat', '.cs', '.java',
    '.aidl', '.gradle', '.xml', '.properties', '.yml', '.yaml',
}
SOURCE_CACHE_DIRS = {
    '__pycache__', '.pytest_cache', 'logs', 'release_test',
    'fixed_candidates', 'originals', 'build', '.gradle',
}


def source_tree_names(folder):
    directory = ROOT / folder
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    return [p.relative_to(ROOT).as_posix() for p in sorted(directory.rglob('*'))
            if p.is_file() and (p.suffix.lower() in SOURCE_SUFFIXES or p.name == 'settings.gradle')
            and not SOURCE_CACHE_DIRS.intersection(p.relative_to(directory).parts[:-1])]


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


def check_text_encoding(path, relative):
    data = path.read_bytes()
    if relative.endswith('.ps1'):
        if not data.startswith(b'\xef\xbb\xbf'):
            raise ValueError(f'PowerShell 脚本缺少 UTF-8 BOM（PS 5.1 必需）：{relative}')
        if b'\n' in data.replace(b'\r\n', b''):
            raise ValueError(f'PowerShell 脚本包含 LF 行尾（应为 CRLF）：{relative}')
    elif relative.endswith('.bat'):
        if data.startswith(b'\xef\xbb\xbf'):
            raise ValueError(f'批处理脚本禁止包含 UTF-8 BOM：{relative}')
        if b'\n' in data.replace(b'\r\n', b''):
            raise ValueError(f'批处理脚本包含 LF 行尾（应为 CRLF）：{relative}')


def archive(path, entries, prefix):
    tmp = path.with_name(path.name + '.tmp')
    if tmp.exists():
        tmp.unlink()
    try:
        with ZipFile(tmp, 'w', ZIP_DEFLATED, compresslevel=6) as package:
            for source, relative in entries:
                package.write(source, f'{prefix}/{relative}')
        with ZipFile(tmp) as package:
            damaged = package.testzip()
            if damaged:
                raise ValueError(f'压缩包校验失败：{damaged}')
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


def refresh_manifest(payload_root=None, language='zhcn'):
    if language == 'zhcn':
        manifest_path = ROOT / 'tools/package-files.json'
        non_payload = CORE_NON_PAYLOAD_PATHS
        prefix = 'payload/'
    else:
        manifest_path = ROOT / f'tools/package-files-{language}.json'
        non_payload = VI_CORE_NON_PAYLOAD_PATHS
        prefix = f'payload-{language}/'

    catalog = json.loads(manifest_path.read_text('utf-8-sig'))
    if catalog.get('format') != 1 or catalog.get('hash') != 'SHA256':
        raise ValueError(f'文件清单格式无效: {manifest_path}')

    by_path = {}
    for item in catalog['files']:
        rel = item['path']
        if rel in by_path:
            raise ValueError(f'重复包内路径：{rel}')
        by_path[rel] = dict(item)

    for rel in non_payload:
        p = ROOT / rel
        if not p.is_file() and language != 'zhcn':
            continue
        src = child(ROOT, rel)
        check_text_encoding(src, rel)
        by_path[rel] = {
            'path': rel,
            'size': src.stat().st_size,
            'sha256': sha256(src),
        }

    if payload_root is not None:
        plen = len(prefix)
        for rel in list(by_path.keys()):
            if rel.startswith(prefix):
                src = child(payload_root, rel[plen:])
                by_path[rel] = {
                    'path': rel,
                    'size': src.stat().st_size,
                    'sha256': sha256(src),
                }
        # For non-zhcn, also include verified jp_deblur payload if present in payload_root/jp_deblur
        if language != 'zhcn':
            deblur_plan = ROOT / 'tools/jp-deblur-deployment.json'
            deblur_dir = payload_root / 'jp_deblur'
            if deblur_plan.is_file() and deblur_dir.is_dir():
                dplan = json.loads(deblur_plan.read_text('utf-8-sig'))
                for fitem in dplan['files']:
                    drel = fitem['relative_path']
                    dsrc = child(deblur_dir, drel)
                    if dsrc.stat().st_size != fitem['size'] or sha256(dsrc) != fitem['target_sha256']:
                        raise ValueError(f'JP Deblur payload SHA mismatch: {drel}')
                    pack_rel = f'{prefix}jp_deblur/{drel}'
                    by_path[pack_rel] = {
                        'path': pack_rel,
                        'size': dsrc.stat().st_size,
                        'sha256': sha256(dsrc),
                    }

    catalog['files'] = [by_path[k] for k in sorted(by_path)]
    text = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    manifest_path.write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    return len(catalog['files']), len(non_payload)


def verify_repo():
    catalog = json.loads((ROOT / 'tools/package-files.json').read_text('utf-8-sig'))
    if catalog.get('format') != 1 or catalog.get('hash') != 'SHA256':
        raise ValueError('文件清单格式无效')

    seen = set()
    non_payload_checked = 0
    payload_count = 0
    for item in catalog['files']:
        rel = item['path']
        if rel in seen:
            raise ValueError(f'重复包内路径：{rel}')
        seen.add(rel)
        if rel.startswith('payload/'):
            payload_count += 1
            continue
        src = child(ROOT, rel)
        check_text_encoding(src, rel)
        if src.stat().st_size != item['size'] or sha256(src) != item['sha256']:
            raise ValueError(f'清单校验失败（请运行 python build_release.py --refresh-manifest）：{rel}')
        non_payload_checked += 1

    for req in CORE_NON_PAYLOAD_PATHS:
        if req not in seen:
            raise ValueError(f'缺少核心清单登记：{req}')

    pairs = [
        ('tools/Apply-CRCZH.ps1', 'CRC工具/crc/Apply-CRCZH.ps1'),
        ('tools/Apply-JPCRCZH.ps1', 'CRC工具/jp_crc/Apply-JPCRCZH.ps1'),
    ]
    for a, b in pairs:
        pa, pb = child(ROOT, a), child(ROOT, b)
        if sha256(pa) != sha256(pb):
            raise ValueError(f'脚本未同步：{a} != {b}')

    return non_payload_checked, payload_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, help='完整包中的 payload 文件夹')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--version', default='v5')
    parser.add_argument('--language', choices=['zhcn', 'vi', 'en'], default='zhcn',
                        help='目标语言版本（默认 zhcn 保持原版完整行为）')
    parser.add_argument('--refresh-manifest', action='store_true', help='刷新 tools/package-files*.json 中非 payload 条目')
    parser.add_argument('--verify-repo', action='store_true', help='校验源码仓库清单、编码规则及 CRC 副本同步')
    args = parser.parse_args()

    if args.refresh_manifest:
        total, updated = refresh_manifest(args.payload, 'zhcn')
        vi_p = ROOT / 'payload-vi'
        vi_total = 0
        if (ROOT / 'tools/package-files-vi.json').is_file():
            vi_total, _ = refresh_manifest(vi_p if vi_p.is_dir() else None, 'vi')
        print(json.dumps({'refreshed': True, 'total_entries': total, 'non_payload_entries': updated, 'vi_entries': vi_total}, ensure_ascii=False))
        if not args.verify_repo and args.payload is None:
            return

    if args.verify_repo:
        non_payload, payload = verify_repo()
        print(json.dumps({'repo_verified': True, 'non_payload_entries': non_payload, 'payload_entries': payload}, ensure_ascii=False))
        if args.payload is None:
            return

    if args.payload is None:
        parser.error('构建发布包需要指定 --payload（或使用 --verify-repo / --refresh-manifest）')

    if not re.fullmatch(r'[A-Za-z0-9._-]+', args.version):
        raise ValueError('版本名称无效')

    if args.language != 'zhcn':
        refresh_manifest(args.payload, args.language)

    catalog_rel = 'tools/package-files.json' if args.language == 'zhcn' else f'tools/package-files-{args.language}.json'
    catalog = json.loads((ROOT / catalog_rel).read_text('utf-8-sig'))
    if catalog.get('format') != 1 or catalog.get('hash') != 'SHA256':
        raise ValueError(f'文件清单格式无效: {catalog_rel}')
    if catalog.get('status') == 'placeholder-no-payload':
        raise ValueError(f'{catalog_rel} 仍为 placeholder-no-payload，请先构建 payload 再打包')

    payload_prefix = 'payload/' if args.language == 'zhcn' else f'payload-{args.language}/'
    plen = len(payload_prefix)

    entries = {}
    for item in catalog['files']:
        relative = item['path']
        if relative in entries:
            raise ValueError(f'重复包内路径：{relative}')
        source = child(args.payload, relative[plen:]) if relative.startswith(payload_prefix) else child(ROOT, relative)
        if not relative.startswith(payload_prefix):
            check_text_encoding(source, relative)
        if source.stat().st_size != item['size'] or sha256(source) != item['sha256']:
            raise ValueError(f'文件校验失败：{relative}')
        entries[relative] = source

    for name in (catalog_rel, 'tools/安装路径.json'):
        if (ROOT / name).is_file():
            entries[name] = child(ROOT, name)

    setup_exe = ROOT / 'AzurPromilia-VI-Setup.exe'
    if args.language == 'vi' and setup_exe.is_file():
        entries['AzurPromilia-VI-Setup.exe'] = setup_exe

    source_names = ['.gitignore', 'LICENSE', 'README.md', 'build_release.py', '双击运行.bat']
    for opt in ('.gitattributes', '使用说明.txt', 'CaiDat-Android-ADB.bat', 'latest-vi.json'):
        if (ROOT / opt).is_file():
            source_names.append(opt)
    for folder in ('tools', 'CRC工具', 'tests', 'installer', 'android-installer'):
        if (ROOT / folder).is_dir():
            source_names += source_tree_names(folder)
    sources = [(child(ROOT, name), name) for name in sorted(set(source_names))]

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.language == 'zhcn':
        full = output / f'AzurPromilia-Localization-Full-{args.version}.zip'
        source = output / f'AzurPromilia-Localization-Source-{args.version}.zip'
        for path in (full, source):
            if path.exists():
                raise FileExistsError(path)
    else:
        full = output / f'AzurPromilia-Localization-Full-{args.language}-{args.version}.zip'
        source = output / f'AzurPromilia-Localization-Source-{args.language}-{args.version}.zip'
        for path in (full, source):
            if path.exists():
                path.unlink()

    package = PACKAGES[args.language]
    archive(full, [(path, name) for name, path in sorted(entries.items())], package)
    archive(source, sources, package + '-源码')

    sums_items = [full, source]
    if args.language == 'vi' and setup_exe.is_file():
        sums_items.append(setup_exe)

    if args.language == 'vi':
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
            gradle_path = ROOT / 'android-installer' / 'app' / 'build.gradle'
            apk_ver_name = args.version
            apk_ver_code = 0
            if gradle_path.is_file():
                gradle_txt = gradle_path.read_text('utf-8')
                m_vc = re.search(r'\bversionCode\s+(\d+)', gradle_txt)
                m_vn = re.search(r'\bversionName\s+"([^"]+)"', gradle_txt)
                if m_vc:
                    apk_ver_code = int(m_vc.group(1))
                if m_vn:
                    apk_ver_name = m_vn.group(1)

            payload_rows = sorted(
                f"{item['relative_path'].replace(chr(92), '/')}:{item['target_sha256'].lower()}\n"
                for item in android_plan['files']
            )
            android_payload_hash = hashlib.sha256(''.join(payload_rows).encode('utf-8')).hexdigest()

            apk_info = None
            if apk_src.is_file():
                shutil.copy2(apk_src, apk_dist)
                sums_items.append(apk_dist)
                apk_info = {
                    'version': apk_ver_name,
                    'version_code': apk_ver_code,
                    'filename': apk_dist.name,
                    'size': apk_dist.stat().st_size,
                    'sha256': sha256(apk_dist),
                    'url': f'{base_dl}/{apk_dist.name}',
                }
            elif apk_dist.is_file():
                sums_items.append(apk_dist)
                apk_info = {
                    'version': apk_ver_name,
                    'version_code': apk_ver_code,
                    'filename': apk_dist.name,
                    'size': apk_dist.stat().st_size,
                    'sha256': sha256(apk_dist),
                    'url': f'{base_dl}/{apk_dist.name}',
                }

            android_obj = {
                'package_name': android_plan.get('package_name', 'com.Yostar.AzurpromiliaJP'),
                'resource_version': android_plan.get('resource_version', '3219596'),
                'payload_hash': android_payload_hash,
                'filename': az_zip.name,
                'size': az_zip.stat().st_size,
                'sha256': sha256(az_zip),
                'url': f'{base_dl}/{az_zip.name}',
            }
            if apk_info:
                android_obj['apk'] = apk_info

        deblur_included = any(name.startswith(f'{payload_prefix}jp_deblur/') for name in entries)
        latest = {
            'schema_version': 1,
            'language': 'vi',
            'version': args.version,
            'published_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'repo': repo_slug,
            'jp_resource_version': '3219598',
            'jp_builtin_version': '3075915',
            'jp_launcher_version': '1.8.1',
            'deblur_supported': deblur_included,
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
            'notes': f'{args.version}: Sửa lỗi hiển thị/lưu phiên bản cũ trên app Windows, hỗ trợ nâng cấp thẳng từ bản cũ (v1.0.0/v1.0.1) & giữ tùy chọn Bỏ làm mờ (Deblur - mặc định tắt).',
        }
        if android_obj:
            latest['android'] = android_obj
        latest_txt = json.dumps(latest, indent=2, ensure_ascii=False) + '\n'
        (ROOT / 'latest-vi.json').write_text(latest_txt, encoding='utf-8')
        (output / 'latest-vi.json').write_text(latest_txt, encoding='utf-8')

    checksums = ''.join(f'{sha256(path)}  {path.name}\n' for path in sums_items)
    (output / 'SHA256SUMS.txt').write_text(checksums, 'ascii')

    print(json.dumps({
        'archives': [str(full), str(source)],
        'package_files': len(entries),
        'replacement_files': sum(name.startswith(payload_prefix) for name in entries),
        'language': args.language,
        'source_files': len(sources),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
