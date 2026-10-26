"""Stem transform/ownership contracts and optional real bundled-model inference.

Set BLAZE_STEM_MODEL_DIR to a staged model directory to run the real model tests.
No model downloads, PyTorch dependency, or live provider access in this suite.
"""
from pathlib import Path
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio import stems


def read_float_wav(path):
    content = path.read_bytes()
    if content[:4] != b'RIFF' or content[8:12] != b'WAVE':
        raise AssertionError('Expected WAV output')
    offset, valid = 12, False
    while offset + 8 <= len(content):
        tag, size = struct.unpack('<4sI', content[offset:offset + 8])
        offset += 8
        if tag == b'fmt ':
            valid = struct.unpack('<HHI', content[offset:offset + 8]) == (3, 2, 44100)
        elif tag == b'data':
            if not valid or size != len(content) - offset:
                raise AssertionError('Incomplete or invalid float WAV output')
            return np.frombuffer(content[offset:], dtype='<f4').reshape(-1, 2)
        offset += size + size % 2
    raise AssertionError('Missing WAV samples')


def make_recording(path, seconds=1, silence=False):
    frames = int(seconds * stems.RATE)
    t = np.arange(frames, dtype=np.float64) / stems.RATE
    pcm = np.column_stack((.15 * np.sin(2 * np.pi * 220 * t),
                           .12 * np.sin(2 * np.pi * 330 * t + .2)))
    if silence:
        pcm[:] = 0
    with wave.open(str(path), 'wb') as output:
        output.setparams((2, 2, stems.RATE, 0, 'NONE', 'not compressed'))
        output.writeframes(np.asarray(pcm * 32767, dtype='<i2').tobytes())
    return frames


class StemContracts(unittest.TestCase):
    def test_stft_roundtrip_preserves_channel_order_length_and_peaks(self):
        rng = np.random.default_rng(8)
        audio = rng.normal(0, .1, (2, stems.SEGMENT)).astype(np.float32)
        audio[0, 0], audio[1, -1] = 1.4, -.9
        features, mean, std, padding = stems.waveform_to_spectrum(audio)
        self.assertEqual(features.shape, (1, 4, 2049, 338))
        # Official SCNet divides the input by std+epsilon but denormalizes
        # predictions with std. Compensate only this documented input epsilon
        # to test the transforms/channel ordering as an exact round trip.
        corrected = features * ((std + 1e-5) / std)
        reconstructed = stems.spectrum_to_waveform(np.repeat(corrected, 4, axis=0), mean, std, padding)
        self.assertEqual(reconstructed.shape, (4, 2, stems.SEGMENT))
        for source in reconstructed:
            np.testing.assert_allclose(source, audio, atol=3e-7, rtol=2e-6)

    def test_missing_or_path_escaping_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'model is missing or damaged'):
                stems.Separator(root)._load(threading.Event())
            manifest = {'model': {'file': '../private.onnx', 'sha256': stems.MODEL_SHA,
                                  'bytes': stems.MODEL_BYTES}, 'license': 'MIT',
                        'sample_rate': stems.RATE, 'segment_samples': stems.SEGMENT,
                        'stems': list(stems.STEMS)}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'model is missing or damaged'):
                stems.Separator(root)._load(threading.Event())

    def test_cancelled_job_does_not_load_models_or_touch_files(self):
        event = threading.Event()
        event.set()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'stems'
            engine = stems.Separator()
            with patch.object(engine, '_load') as load, self.assertRaises(stems.SeparationCancelled):
                engine.separate(Path(directory) / 'missing.wav', output, cancel_event=event)
            load.assert_not_called()
            self.assertFalse(output.exists())

    def test_existing_output_folder_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'song.wav', root / 'output'
            make_recording(source)
            output.mkdir()
            existing = output / 'vocals.wav'
            existing.write_bytes(b'user recording')
            with self.assertRaisesRegex(ValueError, 'new empty output folder'):
                stems.Separator().separate(source, output)
            self.assertEqual(existing.read_bytes(), b'user recording')

    def test_cancelling_decode_stops_the_native_decoder(self):
        process = Mock()
        process.poll.return_value = None
        event = threading.Event()
        event.set()
        with patch.object(stems.subprocess, 'Popen', return_value=process), self.assertRaises(stems.SeparationCancelled):
            stems.Separator()._decode('recording.wav', Path('not-written.f32'), event)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=2)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for local decoding.')
    def test_silence_outputs_are_finite_and_have_exact_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'silence.wav'
            frames = make_recording(source, .2, silence=True)
            engine = stems.Separator(ffmpeg=shutil.which('ffmpeg'))
            with patch.object(engine, '_load'), patch.object(engine, '_predict') as predict:
                result = engine.separate(source, root / 'out')
            predict.assert_not_called()
            self.assertEqual(tuple(result), stems.STEMS)
            for path in result.values():
                audio = read_float_wav(path)
                self.assertEqual(audio.shape, (frames, 2))
                self.assertFalse(np.any(audio))
            self.assertTrue(source.exists())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for local decoding.')
    def test_over_limit_decode_is_rejected_and_partial_results_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'long.wav'
            make_recording(source, 1.2)
            engine = stems.Separator(ffmpeg=shutil.which('ffmpeg'))
            with patch.object(engine, '_load'), patch.object(stems, 'MAX_SECONDS', 1), self.assertRaisesRegex(ValueError, 'one hour'):
                engine.separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertTrue(source.exists())


@unittest.skipUnless(os.environ.get('BLAZE_STEM_MODEL_DIR'), 'Set BLAZE_STEM_MODEL_DIR for real model inference.')
class RealStemModel(unittest.TestCase):
    def test_numpy_pipeline_matches_original_author_waveform_reference(self):
        golden = json.loads((Path(__file__).parent / 'media/scnet-reference.json').read_text())
        audio = (np.random.default_rng(golden['seed']).standard_normal((2, golden['samples']))
                 * golden['scale']).astype(np.float32)
        engine = stems.Separator(os.environ['BLAZE_STEM_MODEL_DIR'])
        event = threading.Event()
        engine._load(event)
        features, mean, std, padding = stems.waveform_to_spectrum(audio)
        predicted = engine._predict(features, event)
        restored = stems.spectrum_to_waveform(predicted[0], mean, std, padding)
        # The reference came from the original author's checkpoint/PyTorch
        # forward, independently of this NumPy/ONNX preprocessing pipeline.
        np.testing.assert_allclose(restored[:, :, golden['indices']], golden['values'],
                                   atol=2e-4, rtol=.005)

    def test_real_model_separates_a_stereo_recording_with_bounded_contexts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'recording.wav'
            frames = make_recording(source, 8.2)
            original = source.read_bytes()
            updates = []
            engine = stems.Separator(os.environ['BLAZE_STEM_MODEL_DIR'], shutil.which('ffmpeg') or 'ffmpeg')
            result = engine.separate(source, root / 'out', progress=lambda value, message: updates.append(value))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(tuple(result), stems.STEMS)
            outputs = [read_float_wav(result[stem]) for stem in stems.STEMS]
            self.assertTrue(all(output.shape == (frames, 2) and np.isfinite(output).all() for output in outputs))
            self.assertGreater(float(np.abs(outputs[2]).max()), .01)
            self.assertGreater(float(np.abs(outputs[2] - outputs[0]).mean()), 1e-4,
                               'Learned stems must not be identical input copies.')
            self.assertEqual(updates[-1], 1)
            self.assertEqual(updates, sorted(updates))


if __name__ == '__main__':
    unittest.main()
