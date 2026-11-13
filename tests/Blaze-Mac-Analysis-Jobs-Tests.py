"""Real Studio worker/store lifecycle with deterministic controlled inference."""
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio
from music_studio.engine import AnalysisCancelled


BUNDLE = SimpleNamespace(structured=False, metadata={'sha256': 'test-model'},
                         manifest={'frontend': {'sha256': 'test-frontend'}})


def result_for(source):
    return {'schema_version': 1, 'duration': 2, 'analysis_seconds': 1,
            'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'engine_version': 'overlap1', 'key': 'C major', 'tempo_bpm': 120,
            'model': {'name': 'Controlled recognition', 'sha256': 'test-model',
                      'frontend_sha256': 'test-frontend'},
            'beats': [0, .5, 1, 1.5], 'chords': [{'start': 0, 'end': 2, 'chord': 'C:maj'}]}


class AnalysisJobsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'Original song.wav'
        self.source.write_bytes(b'original bytes')
        self.other = self.root / 'Other song.wav'
        self.other.write_bytes(b'other bytes')
        self.studio = Studio(self.root / 'data', 'ffmpeg', self.source)
        self.studio.presentation = 'mac'
        self.addCleanup(self.studio.close)
        self.entered, self.release = threading.Event(), threading.Event()
        self.addCleanup(self.release.set)

    def controlled(self):
        entered, release = self.entered, self.release

        class Recognition:
            def __init__(self, *_):
                self.cancelled = threading.Event()

            def cancel(self):
                self.cancelled.set()
                release.set()

            def check(self):
                if self.cancelled.is_set():
                    raise AnalysisCancelled()

            def analyze(self, source, progress):
                self.pinned = source
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Controlled recognition did not resume.')
                self.check()
                return result_for(source)
        return Recognition

    def start(self):
        self.entered.clear()
        self.release.clear()
        self.studio.analyze('powerful')
        self.assertTrue(self.entered.wait(3))
        self.assertTrue(self.studio.state['busy'])

    def finish(self):
        self.release.set()
        self.studio.worker.join(3)
        self.assertFalse(self.studio.worker.is_alive())
        self.assertFalse(self.studio.state['busy'])
        self.assertIsNone(self.studio.analyzer)
        self.assertEqual(list(self.studio.incoming.glob('.analysis-*')), [])

    def test_saved_result_skips_analyzer_and_keeps_saved_corrections(self):
        result = result_for(self.source)
        result['chords'][0].update(chord='D:min', edited=True)
        self.studio.store.save(result)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', side_effect=AssertionError('Cache hit must not load inference')) as factory:
            self.studio.analyze('powerful')
            self.studio.worker.join(3)
            self.assertFalse(self.studio.worker.is_alive())
            factory.assert_not_called()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')
        self.assertEqual(self.studio.state['result']['chords'][0]['chord'], 'D:min')

    def test_changed_source_does_not_reuse_saved_result(self):
        self.studio.store.save(result_for(self.source))
        self.source.write_bytes(b'new audio must be analysed')
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.finish()
        self.assertEqual(self.studio.state['result']['source_sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_changed_model_does_not_reuse_saved_result(self):
        self.studio.store.save(result_for(self.source))
        changed = SimpleNamespace(structured=False, metadata={'sha256': 'new-model'}, manifest=BUNDLE.manifest)
        with patch('music_studio.server.ModelBundle', return_value=changed), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.finish()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')

    def test_cancel_during_cache_lookup_does_not_publish_result(self):
        def saved(_):
            self.studio.cancel_analysis()
            return result_for(self.source)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch.object(self.studio.store, 'load', side_effect=saved), \
                patch('music_studio.server.Analyzer') as factory:
            self.studio.analyze('powerful')
            self.studio.worker.join(3)
            factory.assert_not_called()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'cancelled')
        self.assertIsNone(self.studio.state['result'])

    def test_worker_passes_digest_only_for_its_verified_private_copy(self):
        studio = self.studio
        base = self.controlled()
        class Recognition(base):
            def analyze(inner, source, progress):
                pinned, stamp, digest = inner.verified_input
                self.assertEqual(pinned, source)
                stat = source.stat()
                self.assertEqual(stamp, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
                self.assertEqual(digest, hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(source.parent, studio.incoming)
                return super().analyze(source, progress)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', Recognition):
            self.start()
            self.finish()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')

    def test_switching_source_does_not_attach_old_result_and_return_restores_it(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.studio.open_local_file(self.other)
            self.assertEqual(self.studio.name, 'Other song.wav')
            self.assertIsNone(self.studio.state['result'])
            self.assertTrue(self.studio.state['busy'])
            self.finish()
        self.assertIsNone(self.studio.state['result'])
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')
        self.assertEqual(self.studio.state['analysisTask']['sourceName'], 'Original song.wav')
        self.assertEqual(len(list(self.studio.store.cache.glob('*.json'))), 1)
        self.studio.open_local_file(self.source)
        self.assertEqual(self.studio.state['result']['source_sha256'], hashlib.sha256(b'original bytes').hexdigest())

    def test_replacing_file_after_completed_analysis_does_not_relabel_old_chords(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.finish()
        self.assertIsNotNone(self.studio.state['result'])
        self.source.write_bytes(b'revised mix written by another application')
        self.studio.open_local_file(self.other)
        self.studio.open_local_file(self.source)
        self.assertIsNone(self.studio.state['result'], 'Old chords were restored for revised audio')

    def test_imported_input_can_be_unlinked_during_analysis_without_losing_bytes(self):
        imported = self.studio.incoming / 'upload.wav'
        imported.write_bytes(b'imported original')
        self.studio.select_source(imported, 'Upload.wav', imported=True)
        key = self.studio.source_identity(imported)
        retained = self.root / 'Retained.wav'
        retained.write_bytes(imported.read_bytes())
        self.studio.associate_source_identity(key, retained)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.studio.open_local_file(self.other)
            self.assertFalse(imported.exists())
            self.finish()
        self.studio.select_source(retained, 'Upload.wav')
        self.assertEqual(self.studio.state['result']['source_sha256'], hashlib.sha256(b'imported original').hexdigest())

    def test_cancel_before_analyzer_is_created_and_retry(self):
        def load_model(*_):
            self.entered.set()
            if not self.release.wait(3):
                raise RuntimeError('Model load did not resume.')
            return BUNDLE
        with patch('music_studio.server.ModelBundle', side_effect=load_model), \
                patch('music_studio.server.Analyzer') as constructor:
            self.start()
            self.assertIsNone(self.studio.analyzer)
            self.studio.cancel_analysis()
            self.finish()
            constructor.assert_not_called()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'cancelled')
        self.assertIsNone(self.studio.state['result'])
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.finish()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')

    def test_analysis_failure_on_background_source_does_not_set_other_file_error(self):
        base = self.controlled()

        class Failure(base):
            def analyze(inner, source, progress):
                self.entered.set()
                self.release.wait(3)
                raise ValueError('Controlled invalid audio')
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', Failure):
            self.start()
            self.studio.open_local_file(self.other)
            self.finish()
        self.assertIsNone(self.studio.state['error'])
        self.assertEqual(self.studio.state['analysisTask']['error'], 'Controlled invalid audio')

    def test_same_path_replaced_with_new_bytes_does_not_get_previous_analysis(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.controlled()):
            self.start()
            self.source.write_bytes(b'new file replacing original')
            self.finish()
        self.assertIsNone(self.studio.state['result'])
        self.studio.open_local_file(self.source)
        self.assertIsNone(self.studio.state['result'])

    def test_other_desktop_presentations_use_original_without_extra_copy_or_disk_requirement(self):
        self.studio.presentation = 'desktop'
        base = self.controlled()
        original = self.source

        class Recognition(base):
            def analyze(inner, source, progress):
                self.assertEqual(source, original)
                self.assertEqual(list(self.studio.incoming.glob('.analysis-*')), [])
                return super().analyze(source, progress)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', Recognition), \
                patch('music_studio.server.shutil.disk_usage', side_effect=AssertionError('No copy reserve for desktop')) as usage:
            self.start()
            self.finish()
            usage.assert_not_called()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')
        self.assertEqual(self.studio.state['result']['source_sha256'], hashlib.sha256(original.read_bytes()).hexdigest())

    def test_other_desktop_presentations_still_guard_file_selection(self):
        self.studio.presentation = 'desktop'
        self.studio.state['busy'] = True
        with self.assertRaisesRegex(ValueError, 'Finish or cancel'):
            self.studio.open_local_file(self.other)
        self.studio.state['busy'] = False
        self.assertEqual(self.studio.source, self.source)

    def test_thread_start_failure_closes_input_and_releases_busy_state(self):
        with patch('music_studio.server.threading.Thread.start', side_effect=RuntimeError('start failed')):
            with self.assertRaisesRegex(ValueError, 'background worker'):
                self.studio.analyze('powerful')
        self.assertFalse(self.studio.state['busy'])
        self.assertEqual(self.studio.state['analysisTask']['status'], 'failed')
        self.assertEqual(list(self.studio.incoming.glob('.analysis-*')), [])


if __name__ == '__main__':
    unittest.main()
