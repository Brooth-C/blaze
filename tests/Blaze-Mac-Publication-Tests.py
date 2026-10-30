"""Exercise the workflow's actual publisher without contacting GitHub."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'Brooth-C/blaze'
SOURCE = 'a' * 40
TAG = 'macos-v0.16.0'
ASSET = 'Blaze-Mac-arm64.zip'


def publisher_source():
    workflow = (ROOT / '.github/workflows/macos-app.yml').read_text(encoding='utf-8')
    step = workflow.split('      - name: Publish immutable Apple Silicon Mac build\n', 1)[1]
    script = step.split("          python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
    return textwrap.dedent(script).replace('${{ github.sha }}', SOURCE)


class MacPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='blaze-mac-publication-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        (self.directory / 'artifacts').mkdir()
        (self.directory / 'docs').mkdir()
        self.payload = b'operator-owned tested Apple Silicon app fixture'
        self.asset = self.directory / 'artifacts' / ASSET
        self.asset.write_bytes(self.payload)
        self.digest = hashlib.sha256(self.payload).hexdigest()
        (self.directory / 'docs/RELEASE-0.16.0.md').write_text(
            '# Blaze for Mac 0.16.0\n\nVerified Studio release.\n', encoding='utf-8')
        self.metadata = {
            'id': 42, 'tag_name': TAG, 'target_commitish': SOURCE,
            'draft': False, 'prerelease': False,
            'assets': [{'name': ASSET, 'size': len(self.payload),
                        'digest': 'sha256:' + self.digest, 'state': 'uploaded'}],
        }
        self.existing = None
        self.lookup_error = None
        self.calls = []
        self.latest = None
        self.latest_response = None

    def fake_gh(self, command, **options):
        self.assertEqual(command[0], 'gh', 'Only GitHub subprocesses may run in this fixture')
        self.calls.append(tuple(command))
        if command[1] == 'api':
            endpoint = command[2]
            if endpoint == f'repos/{REPOSITORY}/releases/tags/{TAG}':
                if self.lookup_error is not None:
                    code, message = self.lookup_error
                    return subprocess.CompletedProcess(command, code, '', message)
                if self.existing is None:
                    return subprocess.CompletedProcess(command, 1, '', 'gh: Not Found (HTTP 404)')
                return subprocess.CompletedProcess(command, 0, json.dumps(self.existing), '')
            if endpoint == f'repos/{REPOSITORY}/releases/latest':
                if self.latest_response is not None:
                    return subprocess.CompletedProcess(command, 0, json.dumps(self.latest_response), '')
                return subprocess.CompletedProcess(command, 0, json.dumps(
                    self.existing if self.latest == TAG else {'tag_name': 'v4.5.0'}), '')
            if endpoint == f'repos/{REPOSITORY}/releases/42':
                return subprocess.CompletedProcess(command, 0, json.dumps(self.existing), '')
            self.fail('Unexpected GitHub endpoint: ' + endpoint)
        if command[1:3] == ['release', 'create']:
            self.assertIsNone(self.existing, 'Published assets must not be replaced')
            self.existing = copy.deepcopy(self.metadata)
            if '--latest=true' in command:
                self.latest = TAG
            return subprocess.CompletedProcess(command, 0, '', '')
        if command[1:3] == ['release', 'edit']:
            self.assertIsNotNone(self.existing)
            if '--latest' in command or '--latest=true' in command:
                self.latest = TAG
            return subprocess.CompletedProcess(command, 0, '', '')
        self.fail('Unexpected GitHub mutation: ' + repr(command))

    def execute(self):
        previous = Path.cwd()
        try:
            os.chdir(self.directory)
            with patch.dict(os.environ, GH_REPO=REPOSITORY), patch.object(
                    subprocess, 'run', side_effect=self.fake_gh), contextlib.redirect_stdout(io.StringIO()):
                exec(compile(publisher_source(), str(ROOT / '.github/workflows/macos-app.yml'), 'exec'),
                     {'__name__': '__main__'})
        finally:
            os.chdir(previous)

    def mutations(self):
        return [command for command in self.calls if command[1] != 'api']

    def test_missing_release_creates_only_the_tested_mac_asset_as_stable_latest(self):
        self.execute()
        self.assertEqual(len(self.mutations()), 1)
        command = self.mutations()[0]
        self.assertEqual(command[:5], ('gh', 'release', 'create', TAG, 'artifacts/' + ASSET))
        self.assertIn('--latest=true', command)
        self.assertNotIn('--prerelease', command)
        self.assertNotIn('--draft', command)
        self.assertNotIn('--clobber', command)
        self.assertEqual(command[command.index('--target') + 1], SOURCE)
        self.assertEqual(self.latest, TAG)
        self.assertFalse(self.existing['draft'])
        self.assertFalse(self.existing['prerelease'])
        notes = (self.directory / 'notes.md').read_text(encoding='utf-8')
        self.assertIn(self.digest, notes)
        self.assertIn('Apple Silicon', notes)
        self.assertEqual(self.asset.read_bytes(), self.payload)

    def test_verified_existing_release_is_promoted_without_uploading_assets(self):
        self.existing = copy.deepcopy(self.metadata)
        self.execute()
        self.assertEqual(self.mutations(), [('gh', 'release', 'edit', TAG, '--latest')])
        self.assertEqual(self.latest, TAG)
        self.assertEqual(self.asset.read_bytes(), self.payload)
        self.assertEqual(self.existing, self.metadata)

    def test_source_draft_and_prerelease_mismatches_refuse_all_mutations(self):
        for key, value in [('target_commitish', 'b' * 40), ('draft', True), ('prerelease', True)]:
            with self.subTest(key=key):
                self.calls = []
                self.existing = copy.deepcopy(self.metadata)
                self.existing[key] = value
                with self.assertRaises(AssertionError):
                    self.execute()
                self.assertEqual(self.mutations(), [])

    def test_asset_digest_and_size_mismatches_refuse_all_mutations(self):
        for key, value in [('digest', 'sha256:' + 'b' * 64), ('size', len(self.payload) + 1)]:
            with self.subTest(key=key):
                self.calls = []
                self.existing = copy.deepcopy(self.metadata)
                self.existing['assets'][0][key] = value
                with self.assertRaises(AssertionError):
                    self.execute()
                self.assertEqual(self.mutations(), [])

    def test_missing_existing_asset_refuses_all_mutations(self):
        self.existing = copy.deepcopy(self.metadata)
        self.existing['assets'] = []
        with self.assertRaises((AssertionError, KeyError)):
            self.execute()
        self.assertEqual(self.mutations(), [])

    def test_non_404_lookup_failures_cannot_create_or_promote_a_release(self):
        for failure in [(1, 'gh: Resource not accessible by integration (HTTP 403)'),
                        (1, 'gh: Internal Server Error (HTTP 500)'),
                        (4, 'gh: authentication required'),
                        (1, 'network connection failed')]:
            with self.subTest(error=failure[1]):
                self.calls = []
                self.lookup_error = failure
                with self.assertRaises((AssertionError, RuntimeError, subprocess.CalledProcessError)):
                    self.execute()
                self.assertEqual(self.mutations(), [])

    def test_wrong_final_latest_source_or_release_state_is_reported_as_failure(self):
        for key, value in [('tag_name', 'v4.5.0'), ('target_commitish', 'b' * 40),
                           ('draft', True), ('prerelease', True)]:
            with self.subTest(key=key):
                self.calls = []
                self.existing = None
                self.latest_response = copy.deepcopy(self.metadata)
                self.latest_response[key] = value
                with self.assertRaises(AssertionError):
                    self.execute()
                self.assertEqual(len(self.mutations()), 1)
                self.assertEqual(self.mutations()[0][1:3], ('release', 'create'))
                # A failed verification must not replace or delete published bytes.
                self.assertEqual(self.existing['assets'], self.metadata['assets'])


if __name__ == '__main__':
    unittest.main()
