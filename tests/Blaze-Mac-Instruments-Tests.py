"""Instrument-family partitions, streaming, ownership and real nine-track flow."""
from pathlib import Path
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.instruments import InstrumentSeparator, NineStemSeparator, family_masks, NINE_STEMS, SEGMENT
from music_studio.stems import SeparationCancelled, _write_header


def recording(path, count):
    values = np.random.default_rng(19).integers(-3000, 3000, (count, 2), dtype='<i2')
    with wave.open(str(path), 'wb') as out:
        out.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        out.writeframes(values.tobytes())
    return values.astype('float32') / 32768


def read(path):
    return np.frombuffer(path.read_bytes()[58:], dtype='<f4').reshape(-1, 2)


def write(path, samples):
    with path.open('wb') as out:
        _write_header(out, len(samples))
        out.write(np.asarray(samples, dtype='<f4').tobytes())


class Controlled(InstrumentSeparator):
    def _load(self, event):
        pass

    def _scores(self, features, event):
        # Includes overlapping high-confidence claims. They must compete for
        # the same spectrum, rather than each duplicating the original audio.
        shape = (4, *features.shape[1:3])
        result = np.zeros(shape, dtype='float32')
        result[0] = .8; result[1] = .6; result[2] = .2; result[3] = .1
        result[:, :2] = 0
        return result


class InstrumentTests(unittest.TestCase):
    def test_masks_bound_overlap_and_preserve_unexplained_energy(self):
        scores = np.array([[.2, 2, 0], [.1, 2, 0], [0, 1, 0], [0, 1, 0]], dtype='float32')
        masks = family_masks(scores)
        self.assertTrue((masks >= 0).all())
        self.assertTrue((masks <= 1).all())
        np.testing.assert_allclose(masks.sum(axis=0), 1, atol=1e-7)
        np.testing.assert_allclose(masks[:, 0], [.2, .1, 0, 0, .7], atol=1e-7)
        self.assertEqual(masks[-1, -1], 1)

    def test_invalid_scores_fail_before_writing_estimates(self):
        for invalid in (np.full((4, 2), np.nan), np.full((4, 2), -1), np.zeros((3, 2))):
            with self.assertRaisesRegex(ValueError, 'invalid'):
                family_masks(invalid)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_absent_families_keep_silence_and_do_not_invent_audio(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'silence.wav'
            with wave.open(str(source), 'wb') as out:
                out.setparams((2, 2, 44100, 0, 'NONE', 'not compressed')); out.writeframes(b'\0' * 4096)
            paths = Controlled().separate(source, root / 'out')
            for path in paths.values():
                self.assertTrue((read(path) == 0).all())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_family_streaming_reconstructs_across_context_boundaries(self):
        for count in (137, SEGMENT + 137):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = root / 'mix.wav'
                original = recording(source, count)
                paths = Controlled().separate(source, root / 'out')
                self.assertEqual(list(paths), ['guitar', 'strings', 'brass', 'synths', 'other'])
                tracks = [read(path) for path in paths.values()]
                self.assertTrue(all(track.shape == original.shape and np.isfinite(track).all() for track in tracks))
                np.testing.assert_allclose(sum(tracks), original, atol=1e-7)

    def test_missing_instrument_model_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'missing or damaged'):
                InstrumentSeparator(d)._load(threading.Event())

    def test_nine_pipeline_preserves_first_four_tracks_byte_for_byte(self):
        class Five:
            def __init__(self, *args):
                pass
            def separate(self, source, output_dir, progress, cancel_event):
                output_dir.mkdir()
                result = {}
                for i, name in enumerate(('vocals', 'drums', 'bass', 'piano', 'other')):
                    path = output_dir / (name + '.wav')
                    write(path, np.full((128, 2), .1 * (i + 1), dtype='float32'))
                    result[name] = path
                return result
        class Families:
            def __init__(self, *args):
                pass
            def separate(self, source, output_dir, progress, cancel_event):
                original = read(source)
                output_dir.mkdir()
                result = {}
                for name in ('guitar', 'strings', 'brass', 'synths', 'other'):
                    path = output_dir / (name + '.wav'); write(path, original / 5); result[name] = path
                return result
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'original.wav'
            source.write_bytes(b'original user recording')
            with patch('music_studio.instruments.QualityFiveStemSeparator', Five), patch('music_studio.instruments.InstrumentSeparator', Families):
                result = NineStemSeparator().separate(source, root / 'out')
            self.assertEqual(tuple(result), NINE_STEMS)
            self.assertEqual(set((root / 'out').iterdir()), set(result.values()))
            for i, name in enumerate(('vocals', 'drums', 'bass', 'piano')):
                expected = root / (name + '.reference.wav')
                write(expected, np.full((128, 2), .1 * (i + 1), dtype='float32'))
                self.assertEqual(result[name].read_bytes(), expected.read_bytes())
            np.testing.assert_allclose(sum(read(result[name]) for name in NINE_STEMS[4:]), .5, atol=1e-7)
            self.assertEqual(source.read_bytes(), b'original user recording')

    def test_cancel_does_not_load_or_create_outputs(self):
        event = threading.Event(); event.set()
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'out'
            with self.assertRaises(SeparationCancelled):
                NineStemSeparator().separate('missing.wav', output, cancel_event=event)
            self.assertFalse(output.exists())

    def test_instrument_failure_removes_intermediate_five_tracks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'original.wav'; source.write_bytes(b'original')
            with patch('music_studio.instruments.QualityFiveStemSeparator') as five, patch('music_studio.instruments.InstrumentSeparator') as families:
                five.return_value.separate.return_value = {'other': root / 'other.wav'}
                families.return_value.separate.side_effect = ValueError('Instrument inference failed')
                with self.assertRaisesRegex(ValueError, 'Instrument inference failed'):
                    NineStemSeparator().separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertEqual(source.read_bytes(), b'original')

    @unittest.skipUnless(os.environ.get('BLAZE_REAL_INSTRUMENTS'), 'Real models explicitly requested')
    def test_real_nine_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            original = recording(source, 44100)
            paths = NineStemSeparator(os.environ['BLAZE_STEM_MODEL_DIR']).separate(source, root / 'out')
            self.assertEqual(tuple(paths), NINE_STEMS)
            tracks = [read(path) for path in paths.values()]
            self.assertTrue(all(np.isfinite(track).all() for track in tracks))
            np.testing.assert_allclose(sum(tracks), original, atol=2e-7)


if __name__ == '__main__':
    unittest.main()
