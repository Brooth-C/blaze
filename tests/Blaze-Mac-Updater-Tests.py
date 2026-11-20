"""Update signatures, fail-closed publication, relaunch safety and packaging."""
import ast
import base64
from datetime import datetime, timezone
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import xml.etree.ElementTree as ET

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from music_studio.mac_updates import MacUpdater, RelaunchGate, jobs_busy, configuration
from tools.macos_update_feed import create_feed, NS
from tools.build_macos_studio import write_spec


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'Blaze-Mac-arm64.zip'
        self.archive.write_bytes(b'tested exact archive')
        key = Ed25519PrivateKey.generate()
        self.seed = base64.b64encode(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
        self.public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        self.key = key

    def feed(self):
        return create_feed(self.archive, '0.19.8', self.seed, self.public, datetime(2026, 11, 20, tzinfo=timezone.utc))

    def test_exact_archive_signature_and_reproducible_stable_feed(self):
        payload = self.feed()
        self.assertEqual(payload, self.feed())
        root = ET.fromstring(payload)
        enclosure = root.find('channel/item/enclosure')
        signature = base64.b64decode(enclosure.attrib[f'{{{NS}}}edSignature'])
        self.key.public_key().verify(signature, self.archive.read_bytes())
        with self.assertRaises(InvalidSignature):
            self.key.public_key().verify(signature, b'tampered archive')
        self.assertEqual(int(enclosure.attrib['length']), self.archive.stat().st_size)
        self.assertEqual(enclosure.attrib['url'], 'https://github.com/Brooth-C/blaze/releases/download/macos-v0.19.8/Blaze-Mac-arm64.zip')
        self.assertEqual(root.find(f'channel/item/{{{NS}}}version').text, '0.19.8')
        self.assertIsNone(root.find(f'channel/item/{{{NS}}}channel'))

    def test_cli_missing_secret_refuses_unsigned_feed(self):
        target = self.root / 'mac-appcast.xml'
        env = {k:v for k,v in os.environ.items() if k != 'BLAZE_UPDATE_PRIVATE_KEY'}
        result = subprocess.run([sys.executable, str(ROOT/'tools/macos_update_feed.py'),
            '--archive', str(self.archive), '--version', '0.19.8', '--output', str(target)],
            capture_output=True, text=True, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('refusing unsigned publication', result.stderr)
        self.assertFalse(target.exists())

    def test_wrong_key_cannot_publish(self):
        with self.assertRaises(ValueError):
            create_feed(self.archive, '0.19.8', self.seed, configuration()['public_key'])

    def test_prerelease_and_other_platforms_rejected(self):
        for version in ('0.19.8-beta', '../bad', 'nan'):
            with self.assertRaises(ValueError):
                create_feed(self.archive, version, self.seed, self.public)
        other = self.root / 'Blaze-Windows.zip'
        other.write_bytes(b'other platform')
        with self.assertRaises(ValueError):
            create_feed(other, '0.19.8', self.seed, self.public)

    def test_relaunch_waits_then_runs_once(self):
        calls = []
        gate = RelaunchGate()
        self.assertTrue(gate.defer(lambda: calls.append('installed')))
        self.assertFalse(gate.finish(False))
        self.assertEqual(calls, [])
        self.assertTrue(gate.finish(True))
        self.assertFalse(gate.finish(True))
        self.assertEqual(calls, ['installed'])

    def test_jobs_block_relaunch(self):
        studio = SimpleNamespace(lock=threading.RLock(), closed=False, state={'busy':False},
                                 stems=None, practice_audio=None, downloader=None)
        self.assertFalse(jobs_busy(studio))
        studio.state['busy'] = True
        self.assertTrue(jobs_busy(studio))
        studio.state['busy'] = False
        studio.stems = SimpleNamespace(value={'status':'running'})
        self.assertTrue(jobs_busy(studio))
        studio.stems = None
        audio = SimpleNamespace(lock=threading.RLock(), saving=set(), jobs={'x':{'status':'pending'}})
        studio.practice_audio = audio
        self.assertTrue(jobs_busy(studio))
        audio.jobs['x']['status'] = 'ready'
        self.assertFalse(jobs_busy(studio))
        audio.saving.add('x')
        self.assertTrue(jobs_busy(studio))
        studio.practice_audio = None
        studio.downloader = SimpleNamespace(worker=SimpleNamespace(is_alive=lambda:True))
        self.assertTrue(jobs_busy(studio))

    def test_native_adapter_requires_fresh_idle_and_survives_playback_errors(self):
        studio = SimpleNamespace(lock=threading.RLock(), closed=False, state={'busy':False},
                                 stems=None, practice_audio=None, downloader=None)
        callbacks = []
        view = SimpleNamespace(evaluateJavaScript_completionHandler_=lambda _, callback: callbacks.append(callback))
        window = SimpleNamespace(native=SimpleNamespace(contentView=lambda:object()))
        adapter = MacUpdater(window, studio, {})
        calls = []
        adapter.gate.defer(lambda:calls.append('relaunch'))
        with patch('music_studio.mac_chrome.find_webview', return_value=view), patch('music_studio.mac_updates.time.monotonic') as clock:
            adapter.poll();callbacks.pop()(None, 'web view unavailable')
            self.assertEqual(calls, [])
            clock.return_value = 10
            adapter.poll();callbacks.pop()('true', None)
            clock.return_value = 11
            adapter.poll();callbacks.pop()('false', None)  # playback resumed
            clock.return_value = 20
            adapter.poll();callbacks.pop()('true', None)
            clock.return_value = 21.9
            adapter.poll();callbacks.pop()('true', None)
            self.assertEqual(calls, [])
            clock.return_value = 22
            adapter.poll();callbacks.pop()('true', None)
            self.assertEqual(calls, ['relaunch'])
            adapter.poll()
            self.assertEqual(callbacks, [])

        # A backend job can start while WKWebView evaluates its idle snapshot.
        adapter = MacUpdater(window, studio, {})
        adapter.gate.defer(lambda:calls.append('unsafe'))
        with patch('music_studio.mac_chrome.find_webview', return_value=view):
            adapter.poll()
            studio.state['busy'] = True
            callbacks.pop()('true', None)
        self.assertEqual(calls, ['relaunch'])

    def test_packaged_configuration_uses_public_key_and_no_silent_install(self):
        web = self.root / 'web'
        web.mkdir()
        (web / 'practice-guide.js').write_text('/* fixture */')
        spec = self.root / 'app.spec'
        write_spec(spec, self.root/'entry.py', web, self.root/'models', self.root/'stems', self.root/'icon', [], 'arm64', '0.19.8')
        tree = ast.parse(spec.read_text())
        bundle = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='app' for t in node.targets))
        info = ast.literal_eval(next(k.value for k in bundle.keywords if k.arg=='info_plist'))
        self.assertEqual(info['SUPublicEDKey'], configuration()['public_key'])
        self.assertTrue(info['SUEnableAutomaticChecks'])
        self.assertFalse(info['SUAutomaticallyUpdate'])
        self.assertFalse(info['SUAllowsAutomaticUpdates'])
        self.assertFalse(info['SUEnableSystemProfiling'])
        self.assertEqual(info['SUScheduledCheckInterval'], 86400)
        self.assertEqual(len(base64.b64decode(info['SUPublicEDKey'])), 32)
        self.assertNotIn('private', json.dumps(info).lower())


if __name__ == '__main__':
    unittest.main()
