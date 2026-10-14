"""Reject unvalidated or changed binaries before any release publication."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import promote_mac_release as p


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.head = 'a' * 40
        self.main = 'b' * 40
        self.catalog = {'repository': p.REPOSITORY, 'tag': 'v4.2.1',
                        'assets': [{'name': name, 'source_tag': tag} for name, tag in p.ORIGINS.items()],
                        'macos_validation': {'run_id': 123, 'head_sha': self.head}}
        self.run = {'name': 'Blaze macOS app', 'status': 'completed', 'conclusion': 'success',
                    'head_sha': self.head, 'repository': {'full_name': p.REPOSITORY},
                    'head_repository': {'full_name': p.REPOSITORY}}
        self.jobs = [{'name': 'Mac app / ' + arch, 'conclusion': 'success'} for arch in ('arm64', 'x86_64')]
        self.artifacts = [{'name': 'Blaze-Mac-' + arch, 'expired': False} for arch in ('arm64', 'x86_64')]

    def api(self, endpoint):
        if endpoint.endswith('/jobs?per_page=100'):
            return {'jobs': self.jobs}
        if endpoint.endswith('/artifacts?per_page=100'):
            return {'artifacts': self.artifacts}
        return copy.deepcopy(self.run)

    def validate(self, trees=None):
        with patch.object(p, 'api', side_effect=self.api), patch.object(p, 'input_tree', side_effect=trees or [{'music_studio': 'same'}, {'music_studio': 'same'}]):
            return p.validate(self.catalog, self.main)

    def test_complete_native_proof_is_accepted(self):
        self.assertEqual(self.validate(), (123, self.head))

    def test_changed_app_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.validate([{'music_studio': 'new'}, {'music_studio': 'old'}])

    def test_wrong_or_failed_native_run_is_rejected(self):
        for key, value in [('head_sha', 'c' * 40), ('conclusion', 'failure'), ('status', 'in_progress')]:
            original = self.run[key]
            self.run[key] = value
            with self.assertRaises(ValueError):
                self.validate()
            self.run[key] = original

    def test_missing_architecture_and_expired_artifacts_are_rejected(self):
        self.jobs.pop()
        with self.assertRaisesRegex(ValueError, 'Both native'):
            self.validate()
        self.jobs.append({'name': 'Mac app / x86_64', 'conclusion': 'success'})
        self.artifacts[0]['expired'] = True
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.validate()

    def test_main_advance_is_rejected(self):
        with patch.object(p, 'current_main', return_value='c' * 40):
            with self.assertRaisesRegex(ValueError, 'Main advanced'):
                p.fresh(self.main)

    def test_validation_failure_cannot_publish(self):
        self.catalog['macos_validation']['head_sha'] = 'not-a-commit'
        with patch.dict(p.os.environ, GITHUB_SHA=self.main), patch.object(p, 'current_main', return_value=self.main), patch.object(p, 'publish') as publish:
            with self.assertRaises(ValueError):
                p.promote(self.catalog)
            publish.assert_not_called()

    def test_untagged_draft_is_found_in_release_collection(self):
        draft = {'id': 42, 'tag_name': p.MAC_TAG, 'draft': True}
        with patch.object(p, 'api', return_value=[draft]) as api:
            self.assertEqual(p.find_release(p.MAC_TAG), draft)
            api.assert_called_once_with('releases?per_page=100&page=1')

    def test_release_lookup_pages_and_reports_absent_tag(self):
        older = {'id': 42, 'tag_name': p.MAC_TAG, 'draft': True}
        with patch.object(p, 'api', side_effect=[[{'tag_name': 'old'}] * 100, [older]]):
            self.assertEqual(p.find_release(p.MAC_TAG), older)
        with patch.object(p, 'api', return_value=[]):
            self.assertIsNone(p.find_release(p.MAC_TAG))

    def test_draft_is_verified_and_published_by_id(self):
        draft = {'id': 42, 'tag_name': p.MAC_TAG, 'draft': True, 'prerelease': True,
                 'assets': [{'name': 'Blaze-Mac-arm64.zip'}]}
        final = dict(draft, draft=False)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            notes = directory / 'notes.md'
            notes.write_text('Mac preview notes', encoding='utf-8')
            with patch.object(p, 'find_release', return_value=draft), patch.object(p, 'api', return_value=final) as api, patch.object(p, 'fresh'), patch.object(p.release, 'verify_target') as verify, patch.object(p.release, 'gh') as gh:
                p.publish(p.MAC_TAG, 'Blaze', [{'name': 'Blaze-Mac-arm64.zip'}], directory, notes,
                          self.head, True, self.main)
                gh.assert_called_once_with('api', f'repos/{p.REPOSITORY}/releases/42',
                                           '--method', 'PATCH', '--input', str(directory / 'publish-release.json'))
                api.assert_called_once_with('releases/42')
                self.assertEqual(verify.call_count, 3)
                self.assertEqual(p.json.loads((directory / 'publish-release.json').read_text()),
                                 {'body': 'Mac preview notes', 'draft': False, 'make_latest': 'false'})


if __name__ == '__main__':
    unittest.main()
