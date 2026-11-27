# -*- coding: utf-8 -*-
"""TW 3273850 VI payload integrity, font coverage, and TW VI + TW Deblur coexistence tests."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from fontTools.ttLib import TTFont
import UnityPy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'CRC工具' / 'crc'))
sys.path.insert(0, str(ROOT / 'CRC工具' / 'jp_crc'))
sys.path.insert(0, str(ROOT / 'tests'))

import crcchain as C  # noqa: E402
import vi_codec as V  # noqa: E402
from run_tests import copy_tool_tree, make_crc_matched_pair, run_ps, sha256_bytes  # noqa: E402


def _write_test_manifest(pack_dir: Path, region: str, rel_plan: str, plan: dict) -> None:
    (pack_dir / 'tools' / rel_plan).write_text(json.dumps(plan, indent=2, ensure_ascii=False), 'utf-8')


class TestTWViAndDeblurMerge(unittest.TestCase):
    def test_tw_vi_payload_integrity_and_disjoint_ranges(self):
        tw_vi_plan = json.loads((ROOT / 'tools' / 'tw-deployment-vi.json').read_text('utf-8-sig'))
        tw_deb_plan = json.loads((ROOT / 'tools' / 'tw-deblur-deployment.json').read_text('utf-8-sig'))
        self.assertEqual(tw_vi_plan['status'], 'ready')
        self.assertEqual(tw_vi_plan['resource_version'], '3273850')
        self.assertEqual(len(tw_vi_plan['files']), 14)

        pay_tw = ROOT / 'payload-vi' / 'tw_game'
        for entry in tw_vi_plan['files']:
            p = pay_tw / entry['relative_path']
            self.assertTrue(p.is_file(), f'Missing TW payload file: {entry["relative_path"]}')
            data = p.read_bytes()
            self.assertEqual(len(data), entry['size'], entry['relative_path'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['target_sha256'], entry['relative_path'])
            if 'crc32' in entry:
                self.assertEqual(zlib.crc32(data) & 0xFFFFFFFF, entry['crc32'], entry['relative_path'])

        # Check YooAsset manifests against raw pool, raw table, and rebuilt AST pack
        pairs = [
            ('.res/raw_base_package/ManifestFiles/0release_raw_base_package_3273850.bytes',
             '.res/raw_base_package/ManifestFiles/0release_raw_base_package_3273850.hash',
             '.res/raw_base_package/BundleFiles/qxji39oee8v48b12k5mvq.r'),
            ('.res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3273850.bytes',
             '.res/raw_streaming_package/ManifestFiles/0release_raw_streaming_package_3273850.hash',
             '.res/raw_streaming_package/BundleFiles/obqnmiunqeaffzbzlaj6a.r'),
            ('.res/default_package/ManifestFiles/0release_default_package_3273850.bytes',
             '.res/default_package/ManifestFiles/0release_default_package_3273850.hash',
             '.res/default_package/BundleFiles/4tdqxokz3ihxlqznkg92q.r'),
        ]
        for mf_rel, hash_rel, pack_rel in pairs:
            mf_bytes = (pay_tw / mf_rel).read_bytes()
            hash_bytes = (pay_tw / hash_rel).read_bytes()
            self.assertEqual(hashlib.md5(mf_bytes).hexdigest().encode('ascii'), hash_bytes, hash_rel)
            errs = C.verify(mf_bytes, pay_tw / pack_rel)
            self.assertEqual(errs, [], f'crcchain.verify failed for {pack_rel}: {errs}')

        # Verify VI & Deblur manifest_ranges on default manifest are 100% disjoint
        vi_ranges = next(x['manifest_ranges'] for x in tw_vi_plan['files'] if x.get('manifest_ranges'))
        deb_ranges = next(x['manifest_ranges'] for x in tw_deb_plan['files'] if x.get('manifest_ranges'))
        for r1 in vi_ranges:
            s1, e1 = r1['offset'], r1['offset'] + r1['length']
            for r2 in deb_ranges:
                s2, e2 = r2['offset'], r2['offset'] + r2['length']
                self.assertTrue(e1 <= s2 or e2 <= s1, f'Overlapping manifest_ranges: {(s1, e1)} vs {(s2, e2)}')

        # Verify TW subsetted fonts contain Vietnamese diacritics
        required_vi = set('ắộửđĐẮỘỬ')
        for bundle_rel, expected_names in (
            ('StreamingAssets/.res/default_package/a66pm5ie1rrjguuzlsyq.r', {'a00'}),
            ('StreamingAssets/.res/default_package/p4hifvtlpthiunufa1lslg.r', {'c00'}),
            ('StreamingAssets/.res/static_package/nkewfips4anrz2bqfjhpg.r', {'a00', 'b00', 'c00'}),
        ):
            env = UnityPy.load((pay_tw / bundle_rel).read_bytes())
            seen = set()
            for obj in env.objects:
                if obj.type.name == 'Font':
                    t = obj.read_typetree()
                    nm = t.get('m_Name', '')
                    if nm in expected_names:
                        seen.add(nm)
                        cmap = set((TTFont(io.BytesIO(bytes(t['m_FontData']))).getBestCmap() or {}).keys())
                        for ch in required_vi:
                            self.assertIn(ord(ch), cmap, f'Missing VI glyph {ch!r} in {bundle_rel}:{nm}')
            self.assertEqual(seen, expected_names)

    def _build_synthetic_tw_fixture(self, root: Path):
        pack = root / 'pack'
        copy_tool_tree(pack)
        game = root / 'AzurPromilia_TC'
        data = game / 'AzurPromilia_Data'
        data.mkdir(parents=True)
        (game / 'AzurPromilia.exe').write_bytes(b'TW_EXE')

        # Shared manifest bytes + hash (64 bytes long) modified at disjoint ranges
        mf_rel = '.res/default_package/ManifestFiles/0release_default_package_3273850.bytes'
        hash_rel = '.res/default_package/ManifestFiles/0release_default_package_3273850.hash'
        orig_mf = bytearray(b'TW3273850_MANIFEST_' + bytes(range(64)))[:64]
        vi_mf = bytearray(orig_mf)
        vi_mf[20:24] = b'VI01'
        vi_mf[48:52] = b'VI02'
        deb_mf = bytearray(orig_mf)
        deb_mf[28:32] = b'DB01'
        deb_mf[56:60] = b'DB02'

        orig_hash = hashlib.md5(orig_mf).hexdigest().encode('ascii')
        vi_hash = hashlib.md5(vi_mf).hexdigest().encode('ascii')
        deb_hash = hashlib.md5(deb_mf).hexdigest().encode('ascii')

        vi_orig_r, vi_targ_r, vi_segs = make_crc_matched_pair(b'tw_vi', (4096,))
        deb_orig_r, deb_targ_r, deb_segs = make_crc_matched_pair(b'tw_db', (4096,))

        vi_r_rel = '.res/default_package/BundleFiles/twvi0001.r'
        deb_r_rel = '.res/default_package/BundleFiles/twdeb001.r'

        for rel, b in ((mf_rel, bytes(orig_mf)), (hash_rel, orig_hash), (vi_r_rel, vi_orig_r), (deb_r_rel, deb_orig_r)):
            p = data / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)

        for rel, b in ((mf_rel, bytes(vi_mf)), (hash_rel, vi_hash), (vi_r_rel, vi_targ_r)):
            p = pack / 'payload-vi/tw_game' / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)

        for rel, b in ((mf_rel, bytes(deb_mf)), (hash_rel, deb_hash), (deb_r_rel, deb_targ_r)):
            p = pack / 'payload-vi/tw_deblur' / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)

        vi_plan = {
            'format': 1,
            'region': 'tw',
            'resource_version': '3273850',
            'language': 'vi',
            'status': 'ready',
            'backup_dir': '.vi-tw-3273850-backup',
            'files': [
                {
                    'relative_path': vi_r_rel,
                    'source_sha256': sha256_bytes(vi_orig_r),
                    'target_sha256': sha256_bytes(vi_targ_r),
                    'size': len(vi_orig_r),
                    'crc32': vi_segs[0]['crc32'],
                    'segments': vi_segs,
                },
                {
                    'relative_path': mf_rel,
                    'source_sha256': sha256_bytes(orig_mf),
                    'target_sha256': sha256_bytes(vi_mf),
                    'size': len(orig_mf),
                    'preserve_external_changes': True,
                    'manifest_ranges': [
                        {'offset': 20, 'length': 4, 'target_hex': b'VI01'.hex()},
                        {'offset': 48, 'length': 4, 'target_hex': b'VI02'.hex()},
                    ],
                },
                {
                    'relative_path': hash_rel,
                    'source_sha256': sha256_bytes(orig_hash),
                    'target_sha256': sha256_bytes(vi_hash),
                    'size': 32,
                    'preserve_external_changes': True,
                    'manifest_hash_for': mf_rel,
                },
            ],
            'readonly_files': [],
        }
        deb_plan = {
            'format': 1,
            'region': 'tw',
            'resource_version': '3273850',
            'backup_dir': '.tw-deblur-3273850-backup',
            'files': [
                {
                    'relative_path': deb_r_rel,
                    'source_sha256': sha256_bytes(deb_orig_r),
                    'target_sha256': sha256_bytes(deb_targ_r),
                    'size': len(deb_orig_r),
                    'crc32': deb_segs[0]['crc32'],
                    'segments': deb_segs,
                },
                {
                    'relative_path': mf_rel,
                    'source_sha256': sha256_bytes(orig_mf),
                    'target_sha256': sha256_bytes(deb_mf),
                    'size': len(orig_mf),
                    'preserve_external_changes': True,
                    'manifest_ranges': [
                        {'offset': 28, 'length': 4, 'target_hex': b'DB01'.hex()},
                        {'offset': 56, 'length': 4, 'target_hex': b'DB02'.hex()},
                    ],
                },
                {
                    'relative_path': hash_rel,
                    'source_sha256': sha256_bytes(orig_hash),
                    'target_sha256': sha256_bytes(deb_hash),
                    'size': 32,
                    'preserve_external_changes': True,
                    'manifest_hash_for': mf_rel,
                },
            ],
            'readonly_files': [],
        }
        _write_test_manifest(pack, 'tw', 'tw-deployment-vi.json', vi_plan)
        _write_test_manifest(pack, 'tw', 'tw-deblur-deployment.json', deb_plan)
        return {
            'pack': pack,
            'game': game,
            'data': data,
            'vi_ps': pack / 'tools' / 'Apply-CRCZH.ps1',
            'deb_ps': pack / 'tools' / 'Apply-TWDeblur.ps1',
            'mf_rel': mf_rel,
            'hash_rel': hash_rel,
            'orig_mf': bytes(orig_mf),
            'vi_mf': bytes(vi_mf),
            'deb_mf': bytes(deb_mf),
            'orig_hash': orig_hash,
            'vi_r_rel': vi_r_rel,
            'vi_orig_r': vi_orig_r,
            'vi_targ_r': vi_targ_r,
            'deb_r_rel': deb_r_rel,
            'deb_orig_r': deb_orig_r,
            'deb_targ_r': deb_targ_r,
        }

    def test_tw_vi_and_deblur_coexistence_both_orders(self):
        with tempfile.TemporaryDirectory(prefix='azur_tw_coexist_') as td:
            fx = self._build_synthetic_tw_fixture(Path(td))
            mf_path = fx['data'] / fx['mf_rel']
            hash_path = fx['data'] / fx['hash_rel']

            def run_ok(ps, action):
                r = run_ps(ps, ['-Action', action, '-Language', 'vi', '-Hint', str(fx['game'])], fx['pack'])
                self.assertEqual(r.returncode, 0, r.stdout.decode('utf-8', 'replace'))

            # Order A: Apply VI -> Apply Deblur -> Verify both -> Restore Deblur -> Verify VI -> Restore VI
            run_ok(fx['vi_ps'], 'Apply')
            run_ok(fx['vi_ps'], 'Verify')
            self.assertEqual(mf_path.read_bytes(), fx['vi_mf'])
            self.assertEqual(hash_path.read_bytes(), hashlib.md5(mf_path.read_bytes()).hexdigest().encode('ascii'))

            run_ok(fx['deb_ps'], 'Apply')
            run_ok(fx['vi_ps'], 'Verify')
            run_ok(fx['deb_ps'], 'Verify')
            both_mf = mf_path.read_bytes()
            self.assertEqual(both_mf[20:24], b'VI01')
            self.assertEqual(both_mf[28:32], b'DB01')
            self.assertEqual(hash_path.read_bytes(), hashlib.md5(both_mf).hexdigest().encode('ascii'))

            run_ok(fx['deb_ps'], 'Restore')
            run_ok(fx['vi_ps'], 'Verify')
            run_ok(fx['deb_ps'], 'Verify')
            self.assertEqual(mf_path.read_bytes(), fx['vi_mf'])
            self.assertEqual((fx['data'] / fx['vi_r_rel']).read_bytes(), fx['vi_targ_r'])
            self.assertEqual((fx['data'] / fx['deb_r_rel']).read_bytes(), fx['deb_orig_r'])

            run_ok(fx['vi_ps'], 'Restore')
            self.assertEqual(mf_path.read_bytes(), fx['orig_mf'])
            self.assertEqual(hash_path.read_bytes(), fx['orig_hash'])
            self.assertEqual((fx['data'] / fx['vi_r_rel']).read_bytes(), fx['vi_orig_r'])

            # Order B: Apply Deblur -> Apply VI -> Verify both -> Restore VI -> Verify Deblur -> Restore Deblur
            run_ok(fx['deb_ps'], 'Apply')
            run_ok(fx['vi_ps'], 'Apply')
            run_ok(fx['vi_ps'], 'Verify')
            run_ok(fx['deb_ps'], 'Verify')

            run_ok(fx['vi_ps'], 'Restore')
            run_ok(fx['deb_ps'], 'Verify')
            run_ok(fx['vi_ps'], 'Verify')
            self.assertEqual(mf_path.read_bytes(), fx['deb_mf'])
            self.assertEqual((fx['data'] / fx['deb_r_rel']).read_bytes(), fx['deb_targ_r'])
            self.assertEqual((fx['data'] / fx['vi_r_rel']).read_bytes(), fx['vi_orig_r'])
            self.assertEqual(hash_path.read_bytes(), hashlib.md5(fx['deb_mf']).hexdigest().encode('ascii'))

            run_ok(fx['deb_ps'], 'Restore')
            self.assertEqual(mf_path.read_bytes(), fx['orig_mf'])
            self.assertEqual(hash_path.read_bytes(), fx['orig_hash'])
            self.assertEqual((fx['data'] / fx['deb_r_rel']).read_bytes(), fx['deb_orig_r'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
