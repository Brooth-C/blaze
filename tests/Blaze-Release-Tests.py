"""Release catalog navigation, provenance, integrity and immutable mirroring."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import release_page as r


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.catalog = r.load_catalog()
        self.files = {}
        self.sources = {}
        for expected in [*self.catalog['assets'], self.catalog['android_native_sources']]:
            data = ('fixture-' + expected['name']).encode()
            expected['size'] = len(data)
            expected['sha256'] = hashlib.sha256(data).hexdigest()
            self.files[expected['name']] = data
            (self.directory / expected['name']).write_bytes(data)
            self.sources.setdefault(expected['source_tag'], []).append(self.metadata(expected))
        self.target = {'assets': [], 'draft': False}
        self.uploaded = []
        self.downloaded = []
        self.calls = []
        self.concurrent = False

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def metadata(expected):
        return {'name': expected['name'], 'size': expected['size'],
                'digest': 'sha256:' + expected['sha256'], 'state': 'uploaded'}

    def fake_gh(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == 'api':
            tag = args[1].rsplit('/', 1)[-1]
            if tag == self.catalog['tag']:
                return json.dumps(self.target) if self.target is not None else None
            return json.dumps({'assets': self.sources[tag]})
        if args[1] == 'download':
            destination = Path(args[args.index('--dir') + 1])
            names = [args[index + 1] for index, arg in enumerate(args) if arg == '--pattern']
            self.downloaded.extend(names)
            for name in names:
                (destination / name).write_bytes(self.files[name])
        elif args[1] == 'upload':
            names = [Path(value).name for value in args[3:args.index('--repo')]]
            self.uploaded.extend(names)
            by_name = {asset['name']: asset for asset in self.catalog['assets']}
            self.target['assets'].extend(self.metadata(by_name[name]) for name in names)
            if self.concurrent:
                raise RuntimeError('asset already exists')
        return ''

    def mirror(self):
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', side_effect=self.fake_gh):
            return r.mirror(self.catalog['tag'], self.catalog)

    def test_real_catalog_has_seven_explicit_platform_builds(self):
        catalog = r.load_catalog()
        self.assertEqual('v4.3.3', catalog['tag'])
        self.assertEqual(['Blaze-Windows.zip', 'Blaze-Android-Preview.apk', 'Blaze-Mac-arm64.zip', 'Blaze-Mac-x86_64.zip',
                          'Blaze-Linux-x86_64.tar.gz', 'Blaze-Linux-Installer.zip', 'Blaze-Termux-Installer.zip'],
                         [asset['name'] for asset in catalog['assets']])
        self.assertEqual(['windows-v0.7.0', 'android-v0.11.0', 'macos-v0.7.0-preview', 'macos-v0.7.0-preview', 'linux-v0.7.0-preview', 'v4.1.29', 'v4.1.29'],
                         [asset['source_tag'] for asset in catalog['assets']])
        self.assertEqual(['0.7.0', '0.11.0', '0.7.0-preview', '0.7.0-preview', '0.7.0-preview', '4.1.29', '4.1.29'],
                         [asset['component_version'] for asset in catalog['assets']])
        self.assertEqual({'desktop', 'macos', 'android'}, set(catalog['native_validation']))
        self.assertNotIn('Blaze-Windows-Installer.zip', [asset['name'] for asset in catalog['assets']])

    def test_notes_link_once_to_each_catalog_download_and_show_origins(self):
        result = r.page(self.catalog)
        for asset in self.catalog['assets']:
            self.assertEqual(1, result.count(f"/releases/download/{self.catalog['tag']}/{asset['name']}"))
            self.assertIn(asset['sha256'], result)
            self.assertIn(f"/releases/tag/{asset['source_tag']}", result)
        self.assertIn('distribution refresh', result)
        self.assertIn('Android is debug-signed', result)
        self.assertIn(self.catalog['android_native_sources']['url'], result)
        self.assertNotIn('SHA256SUMS', result)
        self.assertIn('Download tar.gz', result)
        self.assertIn('LINUX-DESKTOP.md', result)
        self.assertIn('debug-signed', result)

    def test_component_versions_come_from_the_catalog(self):
        self.catalog['assets'][0]['component_version'] = '99.0.0'
        self.assertIn('Windows: 99.0.0', r.page(self.catalog))

    def test_invalid_catalog_provenance_is_rejected(self):
        for key, value in [('name', '../evil.zip'), ('source_tag', ''), ('sha256', 'bad'), ('size', 0)]:
            catalog = copy.deepcopy(self.catalog)
            catalog['assets'][0][key] = value
            path = self.directory / 'catalog.json'
            path.write_text(json.dumps(catalog), encoding='utf-8')
            with self.assertRaises(ValueError):
                r.load_catalog(path)

    def test_duplicate_catalog_asset_is_rejected(self):
        catalog = copy.deepcopy(self.catalog)
        catalog['assets'].append(catalog['assets'][0])
        path = self.directory / 'catalog.json'
        path.write_text(json.dumps(catalog), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unique assets'):
            r.load_catalog(path)

    def test_tampered_file_is_rejected_even_with_same_size(self):
        r.verify_files(self.directory, self.catalog['assets'])
        asset = self.catalog['assets'][0]
        (self.directory / asset['name']).write_bytes(b'x' * asset['size'])
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            r.verify_files(self.directory, self.catalog['assets'])

    def test_mirror_cannot_target_an_older_release(self):
        with patch.object(r, 'gh') as mock:
            with self.assertRaisesRegex(ValueError, 'declared tag'):
                r.mirror('v4.1.29', self.catalog)
        mock.assert_not_called()

    def test_missing_or_draft_target_preserves_every_release(self):
        for target in (None, {'assets': [], 'draft': True}):
            self.target = target
            self.calls.clear()
            self.assertFalse(self.mirror())
            self.assertEqual(1, len(self.calls))
            self.assertEqual('api', self.calls[0][0])

    def test_existing_different_binary_is_preserved_without_download(self):
        changed = self.metadata(self.catalog['assets'][0])
        changed['digest'] = 'sha256:other'
        self.target['assets'] = [changed]
        with self.assertRaisesRegex(ValueError, 'existing assets are preserved'):
            self.mirror()
        self.assertEqual(1, len(self.calls))
        self.assertEqual([], self.uploaded)

    def test_changed_origin_is_rejected_before_any_upload(self):
        self.sources[self.catalog['assets'][0]['source_tag']][0]['digest'] = 'sha256:other'
        with self.assertRaises(ValueError):
            self.mirror()
        self.assertEqual([], self.downloaded)
        self.assertEqual([], self.uploaded)

    def test_changed_native_corresponding_sources_are_rejected(self):
        self.sources['v4.1.29'][-1]['size'] += 1
        with self.assertRaises(ValueError):
            self.mirror()
        self.assertEqual([], self.uploaded)

    def test_unexpected_custom_download_is_not_deleted(self):
        self.target['assets'] = [{'name': 'extra.txt'}]
        with self.assertRaisesRegex(ValueError, 'unexpected assets'):
            self.mirror()
        self.assertEqual([{'name': 'extra.txt'}], self.target['assets'])

    def test_partial_mirror_uploads_only_missing_verified_install_downloads(self):
        self.target['assets'] = [self.metadata(self.catalog['assets'][0])]
        self.assertTrue(self.mirror())
        missing = [asset['name'] for asset in self.catalog['assets'][1:]]
        self.assertEqual(missing, self.uploaded)
        self.assertEqual(missing, self.downloaded)
        self.assertNotIn(self.catalog['android_native_sources']['name'], self.uploaded)
        self.assertFalse(any('--clobber' in call for call in self.calls))
        r.verify_target(self.target, self.catalog, require_all=True)

    def test_complete_catalog_never_downloads_or_uploads(self):
        self.target['assets'] = [self.metadata(asset) for asset in self.catalog['assets']]
        self.assertTrue(self.mirror())
        self.assertEqual([], self.downloaded)
        self.assertEqual([], self.uploaded)
        self.assertEqual(1 + len({asset['source_tag'] for asset in self.catalog['assets']}), len(self.calls))

    def test_identical_concurrent_upload_is_accepted(self):
        self.concurrent = True
        self.assertTrue(self.mirror())
        r.verify_target(self.target, self.catalog, require_all=True)

    def test_incomplete_concurrent_upload_is_rejected(self):
        def incomplete(*args, **kwargs):
            if args[0:2] == ('release', 'upload'):
                raise RuntimeError('failed upload')
            return self.fake_gh(*args, **kwargs)
        with patch.object(r, 'gh', side_effect=incomplete):
            with self.assertRaisesRegex(ValueError, 'Missing catalog asset'):
                r.mirror(self.catalog['tag'], self.catalog)

    def test_refresh_edits_notes_without_changing_latest_or_versions(self):
        self.target['assets'] = [self.metadata(asset) for asset in self.catalog['assets']]
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', side_effect=self.fake_gh):
            r.refresh(self.catalog)
        edit = self.calls[-1]
        self.assertEqual(('release', 'edit', self.catalog['tag']), edit[:3])
        for flag in ('--latest', '--prerelease', '--target', '--clobber'):
            self.assertNotIn(flag, edit)

    def test_workflow_maintains_catalog_without_republishing_cli_version(self):
        workflow = (ROOT / '.github/workflows/quality-and-release.yml').read_text(encoding='utf-8')
        publisher = workflow.split('  publish:\n', 1)[1]
        self.assertIn('python tools/release_page.py --refresh', publisher)
        self.assertNotIn('release create', publisher)
        self.assertNotIn('VERSION=$', publisher)
        self.assertNotIn('--latest', publisher)
        self.assertIn('CURRENT_SHA', publisher)


if __name__ == '__main__':
    unittest.main()
