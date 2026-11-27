import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACK = ROOT / 'outputs' / '日服简体汉化-清单只读CRC版'
LIVE = Path(os.environ.get('AZUR_JP_ROOT', r'E:\YostarGames\AZUPRO_JP'))
DATA = LIVE / 'AzurPromiliaJP_Data'
ORIGINAL_BACKUP = LIVE / '.zhcn-jp-3219598-backup'
ORIGINALS = HERE / 'originals'
TEST_ROOT = HERE / 'release_test'
FIX = TEST_ROOT / 'AZUPRO_JP'
FD = FIX / 'AzurPromiliaJP_Data'
BACKUP_NAME = '.zhcn-jp-crc-readonly-3219598-backup'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_child(root, relative):
    root = root.resolve()
    child = root / relative
    if not child.resolve().is_relative_to(root) or child.resolve() == root:
        raise ValueError(f'Path escapes root: {relative}')
    current = child
    while current != root.parent:
        if current.is_symlink() or current.is_junction():
            raise ValueError(f'Reparse path refused: {current}')
        current = current.parent
    return child


def run(action, expect=0, hint=FIX):
    # Every deployment invocation is pinned to a fixture, including negative tests.
    if hint.resolve() not in (FIX.resolve(), FD.resolve(), TEST_ROOT.resolve()):
        raise ValueError('Only isolated fixture hints are allowed')
    safe_child(HERE, 'release_test/AZUPRO_JP/AzurPromiliaJP_Data')
    start = time.monotonic()
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', str(PACK / 'tools/Apply-JPCRCZH.ps1'),
               '-Action', action, '-Hint', str(hint)]
    process = subprocess.run(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=120)
    output = process.stdout.decode('utf-8', 'replace')
    (TEST_ROOT / f'{len(CHECKS):02d}_{action}.log').write_text(output, encoding='utf-8')
    result = {'action': action, 'hint': str(hint), 'exit_code': process.returncode,
              'seconds': round(time.monotonic() - start, 2)}
    print(json.dumps({**result, 'last_lines': output.splitlines()[-3:]}, ensure_ascii=False), flush=True)
    assert process.returncode == expect, (result, output)
    CHECKS.append(result)


CHECKS = []


def verify_fixture(plan, patched):
    for record in plan['files']:
        assert sha(safe_child(FD, record['relative_path'])) == record['target_sha256' if patched else 'source_sha256']
    for record in plan['readonly_files']:
        assert sha(safe_child(FD, record['relative_path'])) == record['sha256']


def load_plan():
    for name in ('tools/jp-deployment.json', 'tools/crc-deployment.json'):
        p = PACK / name
        if p.is_file():
            return json.loads(p.read_text(encoding='utf-8-sig'))
    raise FileNotFoundError(PACK / 'tools/jp-deployment.json')


def main():
    plan = load_plan()
    assert plan['region'] == 'jp'
    assert plan['files'] and plan['readonly_files']
    records = plan['files'] + plan['readonly_files']
    assert len({r['relative_path'].casefold() for r in records}) == len(records)
    # Capture actual live hashes: the installation may already be localized.
    live_before = {r['relative_path']: sha(safe_child(DATA, r['relative_path'])) for r in records}
    safe_child(HERE, 'release_test/AZUPRO_JP/AzurPromiliaJP_Data')
    assert not TEST_ROOT.exists(), 'Use a fresh release_test directory; existing fixtures are never deleted automatically'
    TEST_ROOT.mkdir()
    try:
        FD.mkdir(parents=True)
        (FIX / 'AzurPromiliaJP.exe').write_bytes(b'')  # Identification only; never executed.
        for record in records:
            relative = record['relative_path']
            expected = record.get('source_sha256', record.get('sha256'))
            # Builder snapshots include guards whose originals were absent from backup.
            candidates = [safe_child(ORIGINALS, relative), safe_child(ORIGINAL_BACKUP, relative)]
            source = next((p for p in candidates if p.is_file() and sha(p) == expected), None)
            assert source is not None, f'Original snapshot/backup missing or mismatched: {relative}'
            target = safe_child(FD, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        verify_fixture(plan, False)
        run('ValidatePayload')
        guard = safe_child(FD, plan['readonly_files'][0]['relative_path'])
        saved = guard.read_bytes()
        changed = bytearray(saved or b'\0')
        changed[0] ^= 1
        guard.write_bytes(changed)
        run('Apply', expect=1)
        for record in plan['files']:
            assert sha(safe_child(FD, record['relative_path'])) == record['source_sha256']
        assert not (FIX / BACKUP_NAME).exists(), 'Guard rejection must precede resource backups'
        guard.write_bytes(saved)
        # Deny delete/replace on the second resource, after the first atomic
        # replacement has succeeded. A failed target must not block rollback
        # of successfully replaced files.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        locked = safe_child(FD, plan['files'][1]['relative_path'])
        handle = kernel.CreateFileW(str(locked), 0x80000000, 1, None, 3, 0x80, None)
        assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
        try:
            run('Apply', expect=1)
            verify_fixture(plan, False)
            output = (TEST_ROOT / f'{len(CHECKS)-1:02d}_Apply.log').read_text(encoding='utf-8')
            assert '已回滚到操作前' in output, output
            assert '已写入并校验' in output, 'Failure did not occur after a successful write'
        finally:
            kernel.CloseHandle(handle)
        run('Apply', hint=FD)
        verify_fixture(plan, True)
        run('Verify')
        run('Apply', hint=TEST_ROOT)
        verify_fixture(plan, True)
        run('Restore')
        verify_fixture(plan, False)
        run('Verify', hint=FD)
    finally:
        for relative, expected in live_before.items():
            assert sha(safe_child(DATA, relative)) == expected, f'Live installation changed: {relative}'
    result = {'all_passed': True, 'isolated_fixture': str(FIX),
              'production_installation_unchanged': True,
              'changed_guard_rejected_before_resource_writes': True,
              'apply_and_restore_byte_verified': True,
              'idempotent_apply_verified': True, 'checks': CHECKS}
    result['mid_transaction_write_failure_rollback_verified'] = True
    (TEST_ROOT / '脚本测试报告.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

