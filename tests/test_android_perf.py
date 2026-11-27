"""Regression checks for Android In-Game Performance Unlock manifest & CRC32 payload."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parent.parent


class TestAndroidPerf(unittest.TestCase):
    def test_android_manifests_in_sync_and_valid(self):
        tools_deploy = ROOT / 'tools' / 'android-deployment-vi.json'
        asset_deploy = ROOT / 'android-installer' / 'app' / 'src' / 'main' / 'assets' / 'android-deployment-vi.json'
        self.assertEqual(tools_deploy.read_bytes(), asset_deploy.read_bytes(),
                         'APK bundled android-deployment-vi.json must match tools/android-deployment-vi.json')

        deploy = json.loads(tools_deploy.read_text('utf-8-sig'))
        perf_meta = json.loads((ROOT / 'tools' / 'android-perf-vi.json').read_text('utf-8-sig'))
        entry = next(f for f in deploy['files'] if f['relative_path'] == perf_meta['relative_path'])

        self.assertEqual(entry['size'], perf_meta['size'])
        self.assertEqual(entry['crc32'], perf_meta['crc32'])
        self.assertEqual(entry['source_sha256'], perf_meta['source_sha256'])
        self.assertEqual(entry['target_sha256'], perf_meta['base_vi_sha256'])
        self.assertEqual(entry.get('perf_target_sha256'), perf_meta['target_sha256'])

    def test_built_android_perf_payload_matches_crc_and_tables(self):
        perf_meta = json.loads((ROOT / 'tools' / 'android-perf-vi.json').read_text('utf-8-sig'))
        perf_file = ROOT / 'payload-vi' / 'android_perf' / perf_meta['relative_path']
        base_file = ROOT / 'payload-vi' / 'android_game' / perf_meta['relative_path']
        if not perf_file.is_file() or not base_file.is_file():
            self.skipTest('Local payload-vi/android_perf or android_game binary not present (source-only tree)')

        data = perf_file.read_bytes()
        self.assertEqual(len(data), perf_meta['size'])
        self.assertEqual(zlib.crc32(data) & 0xFFFFFFFF, perf_meta['crc32'])
        self.assertEqual(hashlib.sha256(data).hexdigest(), perf_meta['target_sha256'])

        jp_crc_dir = str(ROOT / 'CRC工具' / 'jp_crc')
        if jp_crc_dir not in sys.path:
            sys.path.insert(0, jp_crc_dir)
        import vi_codec as V
        from build_vi_raw import read_table_index

        _, base_langs, _ = read_table_index(V.decode_mmap(base_file.read_bytes()))
        _, perf_langs, _ = read_table_index(V.decode_mmap(data))
        self.assertEqual(perf_langs, base_langs)
