"""Native complex piano masks, full-band streaming and original-file ownership."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import wave
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.native_piano import NativePianoSeparator, SEGMENT
from music_studio.stems import SeparationCancelled


class Controlled(NativePianoSeparator):
    def _load(self, event):
        pass

    def _mask(self, features, event):
        mask = np.zeros((1, 1, *features.shape[1:]), dtype='float32')
        mask[..., 0] = .5
        mask[..., 1] = .25
        return mask


def write_source(path, count):
    t = np.arange(count) / 44100
    # High-band content distinguishes native full-band inference from the old
    # 11 kHz truncation. This deterministic signal is not a musical quality test.
    audio = np.stack((.1*np.sin(2*np.pi*16000*t), .1*np.sin(2*np.pi*220*t)), axis=1)
    pcm = (audio * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm.tobytes())
    return pcm.astype('float32') / 32768


def read_output(path):
    return np.frombuffer(path.read_bytes()[58:], dtype='<f4').reshape(-1, 2)


class NativePianoTests(unittest.TestCase):
    def test_staging_requires_the_exact_local_artifact_and_never_downloads_it(self):
        from tools.stage_macos_studio import stage_native_piano
        payload = b'controlled artifact bytes'
        head = {'file': 'head-piano.onnx', 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
        with tempfile.TemporaryDirectory() as d, patch('music_studio.native_piano_assets.HEAD', head), patch('tools.stage_macos_studio.fetch', side_effect=AssertionError('Unexpected model download')):
            root = Path(d); cache = root/'cache';cache.mkdir()
            with self.assertRaisesRegex(ValueError, 'Build and verify'):
                stage_native_piano(cache, root/'missing')
            (cache/head['file']).write_bytes(payload)
            stage_native_piano(cache, root/'staged')
            self.assertEqual((root/'staged'/head['file']).read_bytes(), payload)
            self.assertEqual(json.loads((root/'staged/manifest.json').read_text())['head'], head)
            (cache/head['file']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                stage_native_piano(cache, root/'bad')

    def test_native_complex_mask_preserves_phase_and_high_band(self):
        audio = write_values = np.zeros((2, SEGMENT), dtype='float32')
        t = np.arange(SEGMENT) / 44100
        write_values[0] = .1*np.sin(2*np.pi*16000*t)
        write_values[1] = .1*np.sin(2*np.pi*220*t)
        estimates = Controlled()._chunk(audio, threading.Event())
        interior = slice(4096, -4096)
        expected = .05*np.sin(2*np.pi*16000*t) + .025*np.cos(2*np.pi*16000*t)
        np.testing.assert_allclose(estimates[0, 0, interior], expected[interior], atol=2e-6)
        np.testing.assert_allclose(estimates.sum(axis=0), audio, atol=1e-8)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_short_and_long_stereo_reconstruct_with_exact_length(self):
        for count in (137, SEGMENT+137):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = root/'original.wav'
                original = write_source(source, count)
                progress = []
                paths = Controlled().separate(source, root/'out', progress=lambda p, m: progress.append(p))
                self.assertEqual(list(paths), ['piano', 'accompaniment'])
                piano, accompaniment = (read_output(paths[k]) for k in paths)
                self.assertEqual(piano.shape, original.shape)
                np.testing.assert_allclose(piano+accompaniment, original, atol=1e-7)
                self.assertTrue(all(np.isfinite(x).all() for x in (piano, accompaniment)))
                self.assertTrue(all(0 <= p <= 1 for p in progress))
                self.assertTrue(all(a <= b for a, b in zip(progress, progress[1:])))
                self.assertEqual(progress[-1], 1)

    def test_missing_model_never_silently_uses_spleeter(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'missing or damaged'):
                NativePianoSeparator(d)._load(threading.Event())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_bad_mask_and_cancellation_remove_partial_files(self):
        class Invalid(Controlled):
            def _mask(self, features, event):
                return np.full((1, 1, 2, 3, 2), np.nan)
        class Cancelled(Controlled):
            def _mask(self, features, event):
                event.set()
                raise SeparationCancelled('Cancelled')
        for kind, error in ((Invalid, ValueError), (Cancelled, SeparationCancelled)):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = root/'original.wav'; write_source(source, 137)
                original = source.read_bytes()
                with self.assertRaises(error):
                    kind().separate(source, root/'out')
                self.assertEqual(list((root/'out').iterdir()), [])
                self.assertEqual(source.read_bytes(), original)

    @unittest.skipUnless(os.environ.get('BLAZE_REAL_NATIVE_PIANO'), 'Real native model requested explicitly')
    def test_real_native_model_outputs_and_identity(self):
        from music_studio.native_piano_assets import HEAD, manifest
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root/'original.wav'; original = write_source(source, 44100)
            engine = NativePianoSeparator(os.environ['BLAZE_STEM_MODEL_DIR'])
            self.assertEqual(json.loads((engine.piano_directory/'manifest.json').read_text()), manifest())
            paths = engine.separate(source, root/'out')
            piano, accompaniment = (read_output(paths[k]) for k in paths)
            self.assertEqual(piano.shape, original.shape)
            self.assertTrue(np.isfinite(piano).all())
            np.testing.assert_allclose(piano+accompaniment, original, atol=1e-7)
            self.assertIn(HEAD['sha256'], [r['model_sha256'] for r in engine.runtime.records])


if __name__ == '__main__':
    unittest.main()
