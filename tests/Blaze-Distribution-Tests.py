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
        self.catalog = {
            'repository': p.REPOSITORY, 'tag': 'v4.3.0',
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
                p, 'input_tree', side_effect=trees or [dict(same=True)] * 4):
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
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            self.validate([dict(version='new'), dict(version='old')])

    def test_changed_platform_release_digest_or_target_is_rejected(self):
        source = self.sources['windows-v0.7.0']
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
