"""RoFormer transform, long-recording streaming and five-output ownership."""
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
from music_studio.roformer import RoformerSeparator, QualityFiveStemSeparator, SEGMENT
from music_studio.roformer_transform import stft_bands_last, istft_bands_last
from music_studio.stems import SeparationCancelled


def recording(path, count):
    values = np.random.default_rng(37).integers(-4000, 4000, (count, 2), dtype='<i2')
    with wave.open(str(path), 'wb') as output:
        output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        output.writeframes(values.tobytes())
    return values.astype('float32') / 32768


def samples(path):
    raw = path.read_bytes()
    return np.frombuffer(raw[58:], dtype='<f4').reshape(-1, 2)


class Controlled(RoformerSeparator):
    def _load(self, event):
        pass

    def _chunk(self, audio, event):
        return np.stack([audio * fraction for fraction in (.1, .2, .3, .4)])


class RoformerTests(unittest.TestCase):
    def test_missing_model_and_tampered_block_fail_before_inference(self):
        from music_studio.roformer_assets import MODELS
        with tempfile.TemporaryDirectory() as d:
            engine = RoformerSeparator(d)
            with self.assertRaisesRegex(ValueError, 'missing or damaged'):
                engine._load(threading.Event())
            engine.directory.mkdir()
            meta = MODELS['front']
            (engine.directory / meta['file']).write_bytes(b'changed model')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                engine._graph(meta, np.zeros((1,), dtype='float32'), threading.Event())
            self.assertIsNone(engine.session)

    def test_stereo_spectral_transform_matches_original_layout(self):
        audio = np.random.default_rng(9).normal(0, .1, (2, 44100)).astype('float32')
        audio[0, 0], audio[1, -1] = 1.4, -1.2
        spec = stft_bands_last(audio, 2048, 441)
        restored = istft_bands_last(spec[0], 2, 2048, 441, audio.shape[-1])
        np.testing.assert_allclose(restored, audio, atol=1e-7)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_short_and_long_streaming_preserve_duration_alignment_and_mix(self):
        # Exercise zero-padded short clips and reflected borders for recordings
        # longer than a full context; deliberately cross all chunk boundaries.
        for count in (137, SEGMENT + 137, SEGMENT * 2 + 137):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = root / 'mix.wav'
                original = recording(source, count)
                source_bytes = source.read_bytes()
                result = Controlled().separate(source, root / 'out')
                decoded = {name: samples(path) for name, path in result.items()}
                for name, fraction in zip(('drums', 'bass', 'other', 'vocals'), (.1, .2, .3, .4)):
                    self.assertEqual(decoded[name].shape, original.shape)
                    np.testing.assert_allclose(decoded[name], original * fraction, atol=1e-7)
                np.testing.assert_allclose(sum(decoded.values()), original, atol=1e-7)
                self.assertEqual(source.read_bytes(), source_bytes)

    def test_cancel_does_not_load_or_create_outputs(self):
        event = threading.Event(); event.set()
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'out'
            with self.assertRaises(SeparationCancelled):
                QualityFiveStemSeparator().separate('missing.wav', output, cancel_event=event)
            self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_cancel_during_inference_cleans_partial_wavs(self):
        class Cancelled(Controlled):
            def _chunk(self, audio, event):
                event.set()
                raise SeparationCancelled('Cancelled')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            recording(source, 137)
            with self.assertRaises(SeparationCancelled):
                Cancelled().separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertTrue(source.is_file())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_five_outputs_split_remaining_music_and_reconstruct(self):
        from music_studio.piano import PianoSeparator
        class ControlledPiano(PianoSeparator):
            def _graph(self, name, features, event):
                return np.zeros_like(features[0])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            original = recording(source, 44100)
            with patch('music_studio.roformer.RoformerSeparator', Controlled), patch('music_studio.piano.PianoSeparator', ControlledPiano):
                result = QualityFiveStemSeparator().separate(source, root / 'out')
            self.assertEqual(list(result), ['vocals', 'drums', 'bass', 'piano', 'other'])
            self.assertEqual(set((root / 'out').iterdir()), set(result.values()))
            decoded = {name: samples(path) for name, path in result.items()}
            np.testing.assert_allclose(decoded['vocals'], original * .4, atol=1e-7)
            np.testing.assert_allclose(decoded['drums'], original * .1, atol=1e-7)
            np.testing.assert_allclose(decoded['bass'], original * .2, atol=1e-7)
            np.testing.assert_allclose(decoded['piano'] + decoded['other'], original * .3, atol=1e-7)
            np.testing.assert_allclose(sum(decoded.values()), original, atol=1e-7)

    def test_second_stage_failure_cleans_intermediate_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            source.write_bytes(b'original')
            with patch('music_studio.roformer.RoformerSeparator') as main, patch('music_studio.piano.PianoSeparator') as piano:
                main.return_value.separate.return_value = {'other': root / 'remaining.wav'}
                piano.return_value.separate.side_effect = ValueError('Piano inference failed')
                with self.assertRaisesRegex(ValueError, 'Piano inference failed'):
                    QualityFiveStemSeparator().separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertEqual(source.read_bytes(), b'original')

    @unittest.skipUnless(os.environ.get('BLAZE_REAL_ROFORMER'), 'Real model explicitly requested')
    def test_real_five_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            original = recording(source, 44100)
            result = QualityFiveStemSeparator(os.environ['BLAZE_STEM_MODEL_DIR']).separate(source, root / 'out')
            self.assertEqual(set(result), {'vocals', 'drums', 'bass', 'piano', 'other'})
            decoded = [samples(path) for path in result.values()]
            self.assertTrue(all(np.isfinite(track).all() for track in decoded))
            np.testing.assert_allclose(sum(decoded), original, atol=1e-7)


if __name__ == '__main__':
    unittest.main()
