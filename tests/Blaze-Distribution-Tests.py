"""Refuse untested, stale or mismatched platform distributions before publication."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import promote_distribution as p


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.head, self.main = 'a' * 40, 'b' * 40
        self.tree = {path: 'same-' + path for path in p.INPUTS}
        self.catalog = {
            'repository': p.REPOSITORY, 'tag': 'v4.4.0',
            'assets': [dict(name=name, source_tag=tag, size=10, sha256='c' * 64)
                       for name, tag in p.ORIGINS.items()],
            'native_validation': {key: dict(run_id=index, head_sha=self.head)
                                  for index, key in enumerate(p.WORKFLOWS, 1)},
            'android_native_sources': dict(p.NATIVE_SOURCES),
        }
        self.runs = {}
        self.jobs = {}
        for index, (key, (name, jobs)) in enumerate(p.WORKFLOWS.items(), 1):
            self.runs[index] = dict(name=name, status='completed', conclusion='success',
                                   head_sha=self.head, event='push', head_branch='main',
                                   repository=dict(full_name=p.REPOSITORY),
                                   head_repository=dict(full_name=p.REPOSITORY))
            names = set(jobs)
            if key == 'android':
                names |= {'Android tests / API 29', 'Android tests / API 35'}
            self.jobs[index] = [dict(name=name, conclusion='success') for name in names]
        self.sources = {}
        for tag in set(p.ORIGINS.values()):
            assets = [self.metadata(asset) for asset in self.catalog['assets'] if asset['source_tag'] == tag]
            if tag == 'v4.1.29':
                assets += [self.metadata(self.catalog['android_native_sources'])]
            self.sources[tag] = dict(draft=False, target_commitish=self.head, assets=assets)

    @staticmethod
    def metadata(asset):
        return dict(name=asset['name'], size=asset['size'], digest='sha256:' + asset['sha256'], state='uploaded')

    def api(self, endpoint):
        if endpoint.startswith('releases/tags/'):
            return copy.deepcopy(self.sources[endpoint.removeprefix('releases/tags/')])
        run_id = int(endpoint.split('/')[2])
        if '/jobs?' in endpoint:
            return dict(jobs=copy.deepcopy(self.jobs[run_id]))
        return copy.deepcopy(self.runs[run_id])

    def validate(self, trees=None):
        with patch.object(p.publisher, 'api', side_effect=self.api), patch.object(
                p, 'input_tree', side_effect=[self.tree] * 4 if trees is None else trees):
            p.validate(self.catalog, self.main)

    def test_verified_native_sources_and_pinned_assets_are_accepted(self):
        self.validate()

    def test_failed_wrong_source_or_fork_workflow_is_rejected(self):
        for key, value in [('conclusion', 'failure'), ('head_sha', 'd' * 40),
                           ('event', 'pull_request'), ('head_branch', 'other'),
                           ('head_repository', dict(full_name='other/blaze'))]:
            original = self.runs[1][key]
            self.runs[1][key] = value
            with self.assertRaises(ValueError):
                self.validate()
            self.runs[1][key] = original

    def test_both_android_emulators_and_every_publication_must_pass(self):
        for run_id, jobs in self.jobs.items():
            for job in jobs:
                job['conclusion'] = 'skipped'
                with self.assertRaises(ValueError):
                    self.validate()
                job['conclusion'] = 'success'

    def test_changed_app_inputs_are_rejected(self):
        previous = dict(self.tree, music_studio='old')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.validate([self.tree, previous])

    def test_android_only_update_retains_verified_desktop_packages(self):
        previous = dict(self.tree, android='old')
        previous['.github/workflows/android-apk.yml'] = 'old'
        self.validate([self.tree, previous, previous, self.tree])

    def test_android_update_still_requires_matching_android_proof(self):
        previous = dict(self.tree, android='old')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.validate([self.tree, previous, previous, previous])

    def test_shared_engine_changes_invalidate_desktop_proof(self):
        previous = dict(self.tree, music_studio='old', android='old')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.validate([self.tree, previous])

    def test_desktop_host_web_and_documentation_changes_retain_android_proof(self):
        # The parent tree differs for a host or web-only change; each actual
        # shared Android module and model subtree retains its original hash.
        previous = dict(self.tree, music_studio='old')
        for path in ('docs/LINUX-DESKTOP.md', 'tools/build_macos_studio.py',
                     'tools/publish_desktop_release.py', '.github/workflows/macos-app.yml'):
            previous[path] = 'old'
        self.validate([self.tree, self.tree, self.tree, previous])

    def test_each_shared_harmony_module_and_model_change_invalidates_android_proof(self):
        for path in ('music_studio/chords.py', 'music_studio/evidence.py',
                     'music_studio/lv_frontend.py', 'music_studio/structured.py', 'music_studio/models'):
            with self.subTest(path=path):
                previous = dict(self.tree, music_studio='old')
                previous[path] = 'old'
                with self.assertRaisesRegex(ValueError, 'inputs changed'):
                    self.validate([self.tree, self.tree, self.tree, previous])

    def test_each_android_build_or_common_provenance_change_invalidates_android_proof(self):
        for path in p.ANDROID_ONLY_INPUTS | {'LICENSE.txt', 'THIRD-PARTY-NOTICES.md', 'docs/assets/blaze-logo.png'}:
            with self.subTest(path=path):
                previous = dict(self.tree)
                previous[path] = 'old'
                with self.assertRaisesRegex(ValueError, 'inputs changed'):
                    self.validate([self.tree, self.tree, self.tree, previous])

    def test_android_comparison_rejects_missing_shared_inputs(self):
        for path in p.ANDROID_INPUTS:
            with self.subTest(path=path):
                incomplete = dict(self.tree)
                incomplete.pop(path)
                with self.assertRaisesRegex(ValueError, 'Incomplete Android'):
                    p.platform_tree(incomplete, 'android')

    def test_recursive_source_tree_requires_shared_paths_even_for_historical_proof(self):
        entries = [dict(path=path, type='tree' if path in ('music_studio', 'android', 'music_studio/models')
                        else 'blob', sha='c' * 40) for path in p.INPUTS]
        def read(tree):
            with patch.object(p.publisher, 'api', side_effect=[{'tree': {'sha': 'd' * 40}}, tree]):
                return p.input_tree(self.head)
        result = read({'tree': entries})
        self.assertEqual(set(result), set(p.INPUTS))
        self.assertTrue(p.ANDROID_INPUTS <= result.keys())
        for path in ('music_studio/chords.py', 'music_studio/models'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Incomplete application'):
                read({'tree': [entry for entry in entries if entry['path'] != path]})
        with self.assertRaisesRegex(ValueError, 'Incomplete application'):
            read({'tree': entries, 'truncated': True})

    def test_changed_platform_release_digest_or_target_is_rejected(self):
        source = self.sources['windows-v0.8.0']
        source['target_commitish'] = 'e' * 40
        with self.assertRaises(ValueError):
            self.validate()
        source['target_commitish'] = self.head
        source['assets'][0]['digest'] = 'sha256:' + 'e' * 64
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_proof_or_source_archive_is_rejected(self):
        proof = self.catalog['native_validation'].pop('android')
        with self.assertRaises(ValueError):
            self.validate()
        self.catalog['native_validation']['android'] = proof
        self.sources['v4.1.29']['assets'].pop()
        with self.assertRaises(ValueError):
            self.validate()

    def test_different_decoder_source_archive_is_rejected(self):
        self.catalog['android_native_sources']['sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'reviewed native build'):
            self.validate()

    def test_validation_failure_cannot_publish(self):
        with patch.object(p.publisher, 'current_main', return_value=self.main), patch.dict(
                p.os.environ, GITHUB_SHA=self.main), patch.object(p, 'validate', side_effect=ValueError), patch.object(
                p.publisher, 'publish') as publish:
            with self.assertRaises(ValueError):
                p.promote(self.catalog)
            publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
