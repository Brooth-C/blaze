"""A blocked rhythm worker must not hide usable chords or cache them as final."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.engine import AnalysisCancelled
from music_studio.practice_sessions import PracticeSessions
from music_studio.server import Studio


BUNDLE = SimpleNamespace(structured=False, metadata={'sha256': 'staged-model'},
                         manifest={'frontend': {'sha256': 'staged-frontend'}})


def analysis(source, preliminary=False):
    result = {'schema_version': 1, 'duration': 2, 'analysis_seconds': .1,
              'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
              'engine_version': 'overlap1', 'key': 'C major', 'tempo_bpm': None if preliminary else 120,
              'model': {'name': 'Controlled staged recognition', 'sha256': 'staged-model',
                        'frontend_sha256': 'staged-frontend'},
              'beats': [] if preliminary else [0, .5, 1, 1.5],
              'chords': [{'start': 0, 'end': 2, 'chord': 'C:maj' if preliminary else 'G:maj'}]}
    if preliminary:
        result.update(analysis_stage='chords', rhythm_status='pending')
    return result


class ChordsFirstJobsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'Practice.wav'
        self.source.write_bytes(b'practice recording')
        self.other = self.root / 'Other.wav'
        self.other.write_bytes(b'another recording')
        self.studio = Studio(self.root / 'state', 'ffmpeg', self.source)
        self.studio.presentation = 'mac'
        self.practice = PracticeSessions(self.studio)
        self.studio.practice_sessions = self.practice
        self.entered, self.release = threading.Event(), threading.Event()
        self.addCleanup(self.studio.close)
        self.addCleanup(self.release.set)

    def recognizer(self, fail=False, before_preview=None):
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
                if before_preview:
                    before_preview()
                self.check()
                self.chords_ready(analysis(source, preliminary=True))
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Controlled rhythm worker did not resume.')
                self.check()
                if fail:
                    raise ValueError('Controlled rhythm failure')
                return analysis(source)
        return Recognition

    def start(self):
        self.studio.analyze('powerful')
        self.assertTrue(self.entered.wait(3))

    def finish(self):
        self.release.set()
        self.studio.worker.join(3)
        self.assertFalse(self.studio.worker.is_alive())
        self.assertFalse(self.studio.state['busy'])
        self.assertEqual(list(self.studio.incoming.glob('.analysis-*')), [])

    def test_chords_are_visible_before_rhythm_and_final_reuses_identity(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer()), \
                patch('music_studio.server.print', create=True) as logged:
            self.start()
            state = self.studio.state
            self.assertTrue(state['busy'])
            self.assertEqual(state['analysisTask']['phase'], 'rhythm')
            self.assertTrue(state['analysisTask']['chordsReady'])
            preview = state['result']
            self.assertEqual(preview['chords'][0]['chord'], 'C:maj')
            self.assertEqual(preview['rhythm_status'], 'pending')
            self.assertIsNone(preview['tempo_bpm'])
            self.assertEqual(preview['audio_file'], self.source.name)
            self.assertEqual(state['analysisTask']['analysisId'], preview['analysis_id'])
            self.assertIsNone(self.studio.store.load(preview['analysis_id']))
            guide = self.practice.snapshot()['guide']
            self.assertEqual(guide['analysis_stage'], 'chords')
            self.assertEqual(guide['rhythm_status'], 'pending')
            self.finish()
        final = self.studio.state['result']
        self.assertEqual(final['analysis_id'], preview['analysis_id'])
        self.assertNotIn('analysis_stage', final)
        self.assertEqual(final['chords'][0]['chord'], 'G:maj')
        self.assertEqual(final['beats'], [0, .5, 1, 1.5])
        self.assertEqual(self.studio.state['analysisTask']['phase'], 'complete')
        self.assertEqual(self.practice.snapshot()['guide']['rhythm_status'], 'complete')
        self.assertEqual(self.studio.store.load(final['analysis_id'])['chords'], final['chords'])
        timing = json.loads(logged.call_args.args[0].split(' ', 1)[1])
        self.assertGreater(timing['first_chords_seconds'], 0)
        self.assertLess(timing['first_chords_seconds'], timing['total_seconds'])

    def test_stopping_rhythm_keeps_preliminary_chords_and_allows_retry(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer()):
            self.start()
            self.studio.cancel_analysis()
            self.finish()
        state = self.studio.state
        self.assertEqual(state['result']['rhythm_status'], 'cancelled')
        self.assertEqual(state['result']['chords'][0]['chord'], 'C:maj')
        self.assertEqual(state['analysisTask']['status'], 'cancelled')
        self.assertIsNone(self.studio.store.load(state['result']['analysis_id']))
        self.entered.clear()
        self.release.clear()
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer()):
            self.start()
            self.finish()
        self.assertEqual(state['analysisTask']['status'], 'done')
        self.assertEqual(state['result']['chords'][0]['chord'], 'G:maj')

    def test_rhythm_failure_keeps_chords_without_caching_partial_result(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer(fail=True)):
            self.start()
            self.finish()
        state = self.studio.state
        self.assertEqual(state['result']['rhythm_status'], 'failed')
        self.assertEqual(state['result']['chords'][0]['chord'], 'C:maj')
        self.assertEqual(state['analysisTask']['phase'], 'failed')
        self.assertEqual(list(self.studio.store.cache.glob('*.json')), [])

    def test_manual_rhythm_correction_survives_stopping_or_failing_background_rhythm(self):
        correction = {'mode': 'grid', 'numerator': 4, 'denominator': 4, 'offset': 0., 'bpm': 90}
        for fail in (False, True):
            with self.subTest(failure=fail):
                self.entered.clear()
                self.release.clear()
                with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                        patch('music_studio.server.Analyzer', self.recognizer(fail=fail)):
                    self.start()
                    with self.studio.lock:
                        self.studio.state['result'] = self.studio.store.edit_rhythm(self.studio.state['result'], correction)
                    if not fail:
                        self.studio.cancel_analysis()
                    self.finish()
                self.assertEqual(self.studio.state['result']['rhythm_correction'], correction)
                self.assertEqual(self.studio.state['result']['rhythm_status'], 'failed' if fail else 'cancelled')

    def test_source_switch_and_return_keeps_guide_bound_to_original(self):
        def switch():
            self.studio.open_local_file(self.other)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer(before_preview=switch)):
            self.start()
            self.assertIsNone(self.studio.state['result'])
            self.assertIsNone(self.practice.snapshot()['guide'])
            self.studio.open_local_file(self.source)
            self.assertEqual(self.studio.state['result']['rhythm_status'], 'pending')
            self.studio.open_local_file(self.other)
            self.finish()
        self.assertIsNone(self.studio.state['result'])
        self.studio.open_local_file(self.source)
        self.assertEqual(self.studio.state['result']['chords'][0]['chord'], 'G:maj')

    def test_replaced_source_never_receives_preliminary_or_final_guide(self):
        def replace():
            self.source.write_bytes(b'updated song bytes')
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer(before_preview=replace)):
            self.start()
            self.assertIsNone(self.studio.state['result'])
            self.finish()
        self.assertIsNone(self.studio.state['result'])
        self.studio.open_local_file(self.source)
        self.assertIsNone(self.studio.state['result'])

    def test_saving_practice_during_rhythm_does_not_persist_partial_analysis(self):
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', self.recognizer()):
            self.start()
            key = self.studio.source_identity(self.source)
            preview = self.studio.state['result']
            self.practice.remember_analysis(key, preview)
            saved = self.practice.save({'sourceRevision': self.studio.source_revision,
                                        'position': .5, 'rate': 1, 'mode': 'original'})
            row = self.practice.records[saved['saved']['id']]
            self.assertIsNone(row['analysisId'])
            self.assertEqual(self.practice.snapshot()['guide']['rhythm_status'], 'pending')
            self.finish()
        self.assertEqual(row['analysisId'], self.studio.state['result']['analysis_id'])
        restored_studio = Studio(self.studio.directory, 'ffmpeg', self.source)
        self.addCleanup(restored_studio.close)
        restored = PracticeSessions(restored_studio)
        self.assertEqual(restored.snapshot()['guide']['rhythm_status'], 'complete')

    def test_store_rejects_preliminary_result_as_completed_analysis(self):
        with self.assertRaisesRegex(ValueError, 'Preliminary'):
            self.studio.store.save(analysis(self.source, preliminary=True))
        self.assertEqual(list(self.studio.store.cache.glob('*.json')), [])

    def test_other_desktop_does_not_enable_preview_callback(self):
        self.studio.presentation = 'desktop'
        test = self
        class Recognition:
            def __init__(self, *_): pass
            def check(self): pass
            def analyze(self, source, progress):
                test.assertFalse(hasattr(self, 'chords_ready'))
                return analysis(source)
        with patch('music_studio.server.ModelBundle', return_value=BUNDLE), \
                patch('music_studio.server.Analyzer', Recognition):
            self.studio.analyze('powerful')
            self.finish()
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')


if __name__ == '__main__':
    unittest.main()
