"""Release navigation, integrity, immutability and concurrent publishing."""
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
        (ROOT / 'build').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        self.directory = Path(self.temp.name)
        self.files = {'Blaze-Android-Preview.apk': b'fixture-apk',
                      'Blaze-Android-Native-Sources.tar.gz': b'fixture-sources'}
        checksum = hashlib.sha256(self.files[r.ANDROID_FILES[0]]).hexdigest()
        self.files['SHA256SUMS-Android.txt'] = (checksum + '  ' + r.ANDROID_FILES[0] + '\n').encode()
        self.assets = {name: {'name': name, 'state': 'uploaded',
                             'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
                       for name, data in self.files.items()}
        for name, data in self.files.items():
            (self.directory / name).write_bytes(data)

    def tearDown(self):
        self.temp.cleanup()

    def test_notes_contain_only_current_version(self):
        history = '# Blaze 4.1.27\n\n- Current change\n\n# Blaze 4.1.26\n\n- Old change\n'
        result = r.page('4.1.27', '0.2.0-preview', history)
        self.assertIn('Current change', result)
        self.assertNotIn('Old change', result)
        self.assertIn('Blaze-Android-Preview.apk', result)
        with self.assertRaises(ValueError):
            r.current_notes(history, '4.1.28')

    def test_tampered_download_is_rejected(self):
        r.verify_files(self.directory, self.assets)
        (self.directory / r.ANDROID_FILES[0]).write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            r.verify_files(self.directory, self.assets)

    def test_gradle_quote_styles_and_version_parsing(self):
        (self.directory / 'blaze.py').write_text('VERSION = "9.2.1"\n', encoding='utf-8')
        app = self.directory / 'android/app'
        app.mkdir(parents=True)
        for quote in ("'", '"'):
            (app / 'build.gradle').write_text(f'versionName {quote}0.3.0-preview{quote}\n', encoding='utf-8')
            with patch.object(r, 'ROOT', self.directory):
                self.assertEqual(('9.2.1', '0.3.0-preview'), r.versions())

    def test_missing_companion_does_not_upload(self):
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', return_value=None) as mock:
            r.mirror('v4.1.27', '0.2.0-preview')
        self.assertTrue(all(call.args[0] == 'api' for call in mock.call_args_list))

    def test_differing_existing_asset_is_preserved(self):
        source = json.dumps({'assets': list(self.assets.values())})
        target = json.dumps({'assets': [{'name': r.ANDROID_FILES[0], 'digest': 'sha256:other'}]})
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', side_effect=[source, target]) as mock:
            with self.assertRaisesRegex(ValueError, 'already differs'):
                r.mirror('v4.1.27', '0.2.0-preview')
        self.assertEqual(2, mock.call_count)

    def test_partial_mirror_uploads_only_missing_verified_files(self):
        uploaded = []
        def fake(*args, **kwargs):
            if args[0] == 'api':
                return json.dumps({'assets': list(self.assets.values()) if 'android-v' in args[1] else [self.assets[r.ANDROID_FILES[0]]]})
            if args[1] == 'download':
                destination = Path(args[args.index('--dir') + 1])
                for name, data in self.files.items():
                    (destination / name).write_bytes(data)
            elif args[1] == 'upload':
                uploaded.extend(Path(x).name for x in args[3:])
            return ''
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', side_effect=fake), patch.object(r.tempfile, 'TemporaryDirectory', return_value=self.temp):
            r.mirror('v4.1.27', '0.2.0-preview')
        self.assertEqual(set(r.ANDROID_FILES[1:]), set(uploaded))

    def test_concurrent_identical_mirror_is_accepted(self):
        source = json.dumps({'assets': list(self.assets.values())})
        empty = json.dumps({'assets': []})
        calls = iter([source, empty, '', RuntimeError('asset already exists'), source])
        def fake(*args, **kwargs):
            result = next(calls)
            if args[0] == 'release' and args[1] == 'download':
                destination = Path(args[args.index('--dir') + 1])
                for name, data in self.files.items():
                    (destination / name).write_bytes(data)
            if isinstance(result, Exception):
                raise result
            return result
        with patch.dict(r.os.environ, GH_REPO='Brooth-C/blaze'), patch.object(r, 'gh', side_effect=fake), patch.object(r.tempfile, 'TemporaryDirectory', return_value=self.temp):
            r.mirror('v4.1.27', '0.2.0-preview')


if __name__ == '__main__':
    unittest.main()

