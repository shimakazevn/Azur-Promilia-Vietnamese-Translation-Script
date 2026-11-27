"""台服反虚化隔离测试，仅使用临时游戏目录。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import test_jp_deblur


class TestTWDeblur(test_jp_deblur.TestJPDeblur):
    REGION = 'tw'
    LABEL = '台服反虚化'
    GAME_DIR = 'AzurPromilia_TC_game'
    DATA_DIR = 'AzurPromilia_Data'
    EXE_NAME = 'AzurPromilia.exe'
    SCRIPT_NAME = 'Apply-TWDeblur.ps1'
    BACKUP_NAME = '.tw-deblur-3221746-backup'
    APPLY_OPTION = '10'
    RESTORE_OPTION = '11'

    def setUp(self):
        super().setUp()
        self.guard_rel = 'StreamingAssets/.res/default_package/readonly-test.hash'
        self.guard = self.data / self.guard_rel
        self.guard.parent.mkdir(parents=True, exist_ok=True)
        self.guard_bytes = b'ORIGINAL_READONLY_MANIFEST'
        self.guard.write_bytes(self.guard_bytes)
        plan_file = self.pack / 'tools/tw-deblur-deployment.json'
        plan = json.loads(plan_file.read_text('utf-8'))
        plan['readonly_files'] = [dict(relative_path=self.guard_rel,
                                       sha256=hashlib.sha256(self.guard_bytes).hexdigest())]
        plan_file.write_text(json.dumps(plan), 'utf-8')
        self.refresh_catalog()

    def test_modified_readonly_manifest_is_rejected(self):
        self.guard.write_bytes(b'UNKNOWN_MANIFEST')
        self.assertNotEqual(self.invoke('Apply').returncode, 0)
        self.assert_contents(self.originals)
        self.assertEqual(self.guard.read_bytes(), b'UNKNOWN_MANIFEST')
        self.assertFalse(self.backup.exists())

    def test_root_bat_drag_path_install_status_restore(self):
        command = 'cmd.exe /d /s /c ""' + str(self.pack / '双击运行.bat') + '" "' + str(self.game) + '""'
        result = subprocess.run(command, input=b'10\r\n5\r\n11\r\nQ\r\n\r\n',
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=90, cwd=self.pack)
        self.assert_ok(result)
        text = result.stdout.decode('utf-8', 'replace')
        for expected in ('[台服反虚化] 反虚化完成', '已反虚化', '[台服反虚化] 还原完成'):
            self.assertIn(expected, text)
        self.assertEqual(text.count('10. 台服反虚化'), 1)
        self.assert_contents(self.originals)
        self.assertEqual(self.guard.read_bytes(), self.guard_bytes)

    def test_launcher_and_other_region_game_do_not_block_write(self):
        processes = []
        try:
            for name in ('launcher.exe', 'AzurPromiliaJP.exe'):
                exe = self.base / name
                shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', exe)
                processes.append(subprocess.Popen([str(exe), '/d', '/q', '/k'],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW))
            for process in processes:
                self.assertIsNone(process.poll())
            self.assert_ok(self.invoke('Apply'))
            self.assert_contents(self.patched)
            self.assert_ok(self.invoke('Restore'))
            self.assert_contents(self.originals)
        finally:
            for process in processes:
                process.terminate()
                process.wait(timeout=10)
                process.stdin.close()

    def test_main_menu_verify_includes_deblur_after_localization_failure(self):
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.manager)],
            input=b'6\r\nQ\r\n', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=90, cwd=self.pack)
        self.assertEqual(result.returncode, 2, result.stdout.decode('utf-8', 'replace'))
        reports = list((self.pack / 'tools/logs').glob('*/result.json'))
        self.assertEqual(len(reports), 1)
        entries = {item['module']: item for item in json.loads(reports[0].read_text('utf-8-sig'))['results']}
        self.assertEqual(set(entries), {'tw_game', 'tw_deblur'})
        self.assertFalse(entries['tw_game']['success'])
        self.assertTrue(entries['tw_deblur']['success'])
        self.assert_contents(self.originals)
        self.assertEqual(self.guard.read_bytes(), self.guard_bytes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
