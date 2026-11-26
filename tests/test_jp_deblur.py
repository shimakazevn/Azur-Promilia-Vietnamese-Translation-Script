"""日服反虚化隔离测试，仅使用临时游戏目录。"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from run_tests import copy_tool_tree, make_crc_matched_pair, run_ps


class TestJPDeblur(unittest.TestCase):
    REGION = 'jp'
    LABEL = '日服反虚化'
    GAME_DIR = 'AZUPRO_JP'
    DATA_DIR = 'AzurPromiliaJP_Data'
    EXE_NAME = 'AzurPromiliaJP.exe'
    SCRIPT_NAME = 'Apply-JPDeblur.ps1'
    BACKUP_NAME = '.jp-deblur-1.0.2-backup'
    APPLY_OPTION = '8'
    RESTORE_OPTION = '9'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='azur_deblur_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pack = self.base / '中文 空格 (补丁)&!'
        copy_tool_tree(self.pack)
        self.game = self.base / self.GAME_DIR
        self.data = self.game / self.DATA_DIR
        self.data.mkdir(parents=True)
        (self.game / self.EXE_NAME).write_bytes(b'TEST_EXE')
        self.backup = self.game / self.BACKUP_NAME
        self.script = self.pack / 'tools' / self.SCRIPT_NAME
        self.manager = self.pack / 'tools/Manage-Localization.ps1'
        self.originals = {}
        self.patched = {}
        records = []
        for i, rel in enumerate((
            '.res/default_package/BundleFiles/testdeblura.r',
            'StreamingAssets/.res/default_package/testdeblurb.r',
            'StreamingAssets/.res/default_package/testdeblurc.r',
            'StreamingAssets/.res/default_package/testdeblurd.r',
        )):
            original, patched, segments = make_crc_matched_pair(f'deblur{i}'.encode(), (4096,))
            self.originals[rel] = original
            self.patched[rel] = patched
            for root, content in ((self.data, original), (self.pack / f'payload/{self.REGION}_deblur', patched)):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            records.append(dict(relative_path=rel, size=len(original),
                                source_sha256=hashlib.sha256(original).hexdigest(),
                                target_sha256=hashlib.sha256(patched).hexdigest(),
                                crc32=segments[0]['crc32'], segments=segments if self.REGION == 'tw' else []))
        plan = dict(format=1, region=self.REGION, resource_version='', files=records, readonly_files=[])
        (self.pack / f'tools/{self.REGION}-deblur-deployment.json').write_text(json.dumps(plan), 'utf-8')
        paths = {key: str(self.base / ('missing_' + key))
                 for key in ('tw_game', 'jp_game', 'tw_launcher', 'jp_launcher')}
        paths[self.REGION + '_game'] = str(self.game)
        (self.pack / 'tools/安装路径.json').write_text(json.dumps(paths), 'utf-8')
        self.refresh_catalog()

    def refresh_catalog(self):
        catalog_path = self.pack / 'tools/package-files.json'
        catalog = json.loads(catalog_path.read_text('utf-8-sig'))
        files = [item for item in catalog['files'] if not item['path'].startswith('payload/')]
        for item in files:
            path = self.pack / item['path']
            item.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for path in (self.pack / 'payload').rglob('*.r'):
            files.append(dict(path=path.relative_to(self.pack).as_posix(), size=path.stat().st_size,
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        catalog['files'] = files
        catalog_path.write_text(json.dumps(catalog), 'utf-8')

    def invoke(self, action, manager=True):
        args = ['-Action', action]
        if manager:
            args += ['-Target', self.REGION + '_deblur', '-Quiet']
        elif action != 'ValidatePayload':
            args += ['-Hint', str(self.game)]
        return run_ps(self.manager if manager else self.script, args, self.pack)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout.decode('utf-8', 'replace'))

    def assert_contents(self, mapping):
        for rel, expected in mapping.items():
            self.assertEqual((self.data / rel).read_bytes(), expected, rel)

    def test_apply_verify_repeat_restore_without_payload(self):
        self.assert_ok(self.invoke('ValidatePayload'))
        self.assert_ok(self.invoke('Verify'))
        result = self.invoke('Apply')
        self.assert_ok(result)
        self.assertIn('反虚化完成', result.stdout.decode('utf-8', 'replace'))
        self.assert_contents(self.patched)
        for rel, expected in self.originals.items():
            self.assertEqual((self.backup / rel).read_bytes(), expected)
        result = self.invoke('Apply')
        self.assert_ok(result)
        self.assertIn('已反虚化，跳过', result.stdout.decode('utf-8', 'replace'))
        self.assert_ok(self.invoke('Verify'))
        shutil.rmtree(self.pack / 'payload')
        self.assert_ok(self.invoke('Restore'))
        self.assert_contents(self.originals)
        self.assert_ok(self.invoke('Restore'))

    def test_menu_independent_actions_and_status(self):
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.manager)],
            input=f'{self.APPLY_OPTION}\r\n5\r\n{self.RESTORE_OPTION}\r\nQ\r\n'.encode(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=90, cwd=self.pack)
        self.assert_ok(result)
        text = result.stdout.decode('utf-8', 'replace')
        for expected in (f'{self.APPLY_OPTION}. {self.LABEL}', f'{self.RESTORE_OPTION}. 还原{self.LABEL}',
                         f'[{self.LABEL}] 反虚化完成', '已反虚化', f'[{self.LABEL}] 还原完成'):
            self.assertIn(expected, text)
        self.assertEqual(text.count(f'{self.APPLY_OPTION}. {self.LABEL}'), 1)
        self.assert_contents(self.originals)

    def test_default_all_does_not_install_deblur(self):
        result = run_ps(self.manager, ['-Action', 'Apply', '-Quiet'])
        self.assertNotEqual(result.returncode, 0)  # The four localization modules have no fixtures.
        logs = list((self.pack / 'tools/logs').glob('*/result.json'))
        self.assertEqual(len(logs), 1)
        report = json.loads(logs[0].read_text('utf-8-sig'))
        self.assertEqual({entry['module'] for entry in report['results']},
                         {'tw_game', 'jp_game', 'tw_launcher', 'jp_launcher'})
        self.assert_contents(self.originals)
        self.assertFalse(self.backup.exists())

    def test_corrupt_payload_is_rejected_before_write(self):
        rel = list(self.patched)[-1]
        (self.pack / f'payload/{self.REGION}_deblur' / rel).write_bytes(b'BROKEN')
        self.assertNotEqual(self.invoke('Apply').returncode, 0)
        self.assert_contents(self.originals)
        self.assertFalse(self.backup.exists())

    def test_unknown_local_file_is_rejected_before_write(self):
        rel = list(self.originals)[-1]
        changed = b'X' + self.originals[rel][1:]
        (self.data / rel).write_bytes(changed)
        self.assertNotEqual(self.invoke('Apply').returncode, 0)
        expected = dict(self.originals, **{rel: changed})
        self.assert_contents(expected)
        self.assertFalse(self.backup.exists())

    def test_running_game_blocks_write_but_not_noop(self):
        self.assert_ok(self.invoke('Apply'))
        exe = self.game / self.EXE_NAME
        shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', exe)
        process = subprocess.Popen([str(exe), '/d', '/q', '/k'], stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertIsNone(process.poll())
            self.assert_ok(self.invoke('Apply'))
            result = self.invoke('Restore')
            self.assertNotEqual(result.returncode, 0)
            self.assert_contents(self.patched)
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdin.close()

    def test_write_failure_rolls_back_all_changed_files(self):
        self.assert_ok(self.invoke('Apply'))
        path = self.data / list(self.patched)[1]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            result = self.invoke('Restore', manager=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('已回滚到操作前', result.stdout.decode('utf-8', 'replace'))
            self.assert_contents(self.patched)
        finally:
            kernel.CloseHandle(handle)
        self.assert_ok(self.invoke('Restore'))
        self.assert_contents(self.originals)


if __name__ == '__main__':
    unittest.main(verbosity=2)
