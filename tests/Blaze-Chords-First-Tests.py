"""Chord-first delivery must preserve final recognition and release resources."""
import copy
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.engine import Analyzer, AnalysisCancelled, chord_events
from music_studio.store import validate


class ChordsFirstTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pcm = (np.sin(np.arange(30001) * .1) * 1000).astype('<i2')
        self.duration = len(self.pcm) / 22050
        payload = io.BytesIO()
        with wave.open(payload, 'wb') as stream:
            stream.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            stream.writeframes(self.pcm.tobytes())
        self.payload = payload.getvalue()
        self.source = self.root / 'song.wav'
        self.source.write_bytes(self.payload)
        (self.root / 'rhythm_manifest.json').write_text('{}')

    def fixture(self, rhythm_error=None):
        events = []
        heads = [np.full((59, 3), .5, dtype=np.float32)]
        audio = self.pcm.astype(np.float32) / 32768
        baseline_inputs = []

        def decode(actual_heads, baseline, labels, duration, beats, pcm, check):
            check()
            self.assertIs(actual_heads, heads)
            self.assertIs(pcm, audio)
            self.assertEqual(duration, self.duration)
            self.assertEqual(labels, ['C:maj', 'N'])
            self.assertTrue(np.all(actual_heads[0] == .5))
            baseline_inputs.append(baseline)
            events.append('decode-final' if beats else 'decode-initial')
            return [{'start': 0., 'end': duration, 'chord': 'D:min' if beats else 'C:maj',
                     'model_score': .75, 'edited': False}]

        def predict(*args):
            events.append('ensemble')
            return heads

        recognizer = Mock(
            features=Mock(return_value=(np.zeros((59, 252), np.float32), audio)),
            predict_features=Mock(side_effect=predict),
            decode=Mock(side_effect=decode),
            close=Mock(side_effect=lambda: events.append('ensemble-audio-closed')))

        def finish(*args):
            events.append('rhythm')
            self.assertIn('baseline-closed', events)
            if rhythm_error:
                raise rhythm_error
            return {'beats': [.1, .6, 1.1], 'downbeats': [.1], 'tempo_bpm': 120.,
                    'rhythm_model_sha256': 'controlled-rhythm'}

        rhythm = Mock(finish=Mock(side_effect=finish), close=Mock(side_effect=lambda: events.append('rhythm-closed')))
        bundle = SimpleNamespace(
            directory=self.root, structured=recognizer,
            frontend=Mock(close=lambda: events.append('baseline-closed')), network=Mock(),
            metadata={'classes': 2, 'labels': ['C:maj', 'N'], 'name': 'Test', 'version': '1', 'sha256': 'model'},
            manifest={'models': {'extended': {'labels': ['C:maj', 'N']}}, 'frontend': {'sha256': 'frontend'}},
            predict=Mock(side_effect=lambda pcm: np.tile(np.array([[1., 0.]], np.float32), ((len(pcm)+2047)//2048, 1))),
            close=Mock())
        process = Mock(stdout=io.BytesIO(self.payload), wait=Mock(return_value=0), poll=Mock(return_value=0))
        return SimpleNamespace(events=events, bundle=bundle, recognizer=recognizer,
                               rhythm=rhythm, process=process, baseline_inputs=baseline_inputs)

    def run_analysis(self, fixture, callback=None):
        analyzer = Analyzer(fixture.bundle, 'ffmpeg')
        analyzer.chords_ready = callback
        with patch('music_studio.engine.subprocess.Popen', return_value=fixture.process), \
                patch('music_studio.engine.RhythmDetector', return_value=fixture.rhythm):
            return analyzer.analyze(self.source)

    def test_full_chords_arrive_before_rhythm_and_final_matches_original_order(self):
        reference_fixture = self.fixture()
        reference = self.run_analysis(reference_fixture)
        fixture = self.fixture()
        previews = []

        def publish(value):
            validate(value)
            self.assertNotIn('rhythm', fixture.events)
            self.assertIn('ensemble', fixture.events)
            self.assertEqual(fixture.recognizer.predict_features.call_count, 1)
            fixture.events.append('published')
            previews.append(copy.deepcopy(value))
            # The consumer owns its result. It cannot corrupt final metadata,
            # waveform or model predictions through a shared mutable object.
            value['waveform'][0] = 999
            value['model']['sha256'] = 'changed'
            value['chords'][0]['chord'] = 'F:maj'

        final = self.run_analysis(fixture, publish)
        validate(final)
        self.assertEqual(len(previews), 1)
        self.assertEqual(previews[0]['analysis_stage'], 'chords')
        self.assertEqual(previews[0]['rhythm_status'], 'pending')
        self.assertEqual(previews[0]['beats'], [])
        self.assertIsNone(previews[0]['tempo_bpm'])
        self.assertEqual(previews[0]['chords'][0]['chord'], 'C:maj')
        self.assertEqual(final['chords'][0]['chord'], 'D:min')
        self.assertLess(fixture.events.index('published'), fixture.events.index('rhythm'))
        self.assertLess(reference_fixture.events.index('rhythm'), reference_fixture.events.index('ensemble'))
        self.assertNotIn('analysis_stage', final)
        self.assertNotIn('rhythm_status', final)
        self.assertEqual({k: v for k, v in final.items() if k != 'analysis_seconds'},
                         {k: v for k, v in reference.items() if k != 'analysis_seconds'})
        fixture.recognizer.features.assert_called_once()
        fixture.recognizer.predict_features.assert_called_once()
        fixture.bundle.predict.assert_called_once()
        fixture.rhythm.finish.assert_called_once()
        self.assertEqual(fixture.recognizer.decode.call_count, 2)
        self.assertIs(fixture.baseline_inputs[0], fixture.baseline_inputs[1])

    def test_cancel_after_preliminary_chords_stops_before_rhythm(self):
        fixture = self.fixture()
        analyzer = Analyzer(fixture.bundle, 'ffmpeg')
        previews = []

        def publish(value):
            previews.append(value)
            analyzer.cancel()

        analyzer.chords_ready = publish
        with patch('music_studio.engine.subprocess.Popen', return_value=fixture.process), \
                patch('music_studio.engine.RhythmDetector', return_value=fixture.rhythm), \
                self.assertRaises(AnalysisCancelled):
            analyzer.analyze(self.source)
        self.assertEqual(len(previews), 1)
        fixture.rhythm.finish.assert_not_called()
        fixture.rhythm.close.assert_called()
        fixture.recognizer.close.assert_called()
        fixture.bundle.close.assert_called_once()
        self.assertIsNone(analyzer.process)

    def test_rhythm_failure_does_not_mutate_already_delivered_chords(self):
        fixture = self.fixture(rhythm_error=ValueError('Controlled rhythm failure'))
        previews = []
        with self.assertRaisesRegex(ValueError, 'Controlled rhythm failure'):
            self.run_analysis(fixture, previews.append)
        self.assertEqual(len(previews), 1)
        validate(previews[0])
        self.assertEqual(previews[0]['chords'][0]['chord'], 'C:maj')
        fixture.recognizer.close.assert_called()
        fixture.rhythm.close.assert_called()
        fixture.bundle.close.assert_called_once()

    def test_baseline_only_model_also_delivers_chords_before_rhythm(self):
        fixture = self.fixture()
        fixture.bundle.structured = None
        previews = []
        final = self.run_analysis(fixture, lambda value: (fixture.events.append('published'), previews.append(value)))
        self.assertEqual(len(previews), 1)
        validate(previews[0])
        self.assertEqual(previews[0]['beats'], [])
        self.assertEqual(final['beats'], [.1, .6, 1.1])
        self.assertEqual(previews[0]['chords'], final['chords'])
        self.assertLess(fixture.events.index('published'), fixture.events.index('rhythm'))

    def test_no_rhythm_model_finishes_without_an_unnecessary_preview(self):
        fixture = self.fixture()
        (self.root / 'rhythm_manifest.json').unlink()
        fixture.bundle.structured = None
        preview = Mock()
        final = self.run_analysis(fixture, preview)
        preview.assert_not_called()
        fixture.rhythm.finish.assert_not_called()
        validate(final)

    def test_postprocessing_does_not_mutate_frames_used_by_another_stage(self):
        frames = [{'start': i*.1, 'end': (i+1)*.1, 'chord': chord, 'model_score': .9}
                  for i, chord in enumerate(['C:maj', 'D:min', 'C:maj', 'C:maj'])]
        original = copy.deepcopy(frames)
        events = chord_events(frames)
        self.assertEqual(frames, original)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['chord'], 'C:maj')
        self.assertIsNone(events[0]['model_score'])


if __name__ == '__main__':
    unittest.main()
