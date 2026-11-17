"""Native complex piano masks, full-band streaming and original-file ownership."""
import json
import hashlib
import os
import runpy
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import wave
import weakref
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.native_piano import NativePianoSeparator, SEGMENT, apply_complex_mask, piano_and_backing
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
    def test_reconstruction_releases_input_and_model_mask_before_inverse_fft(self):
        refs={}
        def transform(*args):
            value=np.zeros((1,2050,1723,2),np.float32)
            refs['features']=weakref.ref(value)
            return value
        def mask(*args):
            value=np.ones((1,1,2050,1723,2),np.float32)
            refs['mask']=weakref.ref(value)
            return value
        def inverse(spectrum,*args):
            self.assertIsNone(refs['features']())
            self.assertIsNone(refs['mask']())
            self.assertTrue(spectrum.flags.owndata)
            self.assertFalse(np.any(spectrum))
            return np.zeros((2,SEGMENT),np.float64)
        engine=Controlled()
        with patch('music_studio.native_piano.stft_bands_last',side_effect=transform), \
             patch.object(engine,'_mask',new=mask), \
             patch('music_studio.native_piano.istft_bands_last',side_effect=inverse):
            audio=np.zeros((2,SEGMENT),np.float32)
            output=engine._chunk(audio,threading.Event())
        np.testing.assert_array_equal(output,np.zeros((2,2,SEGMENT),np.float32))

    def test_direct_piano_stems_preserve_residual_precision_and_owned_output(self):
        rng=np.random.default_rng(179)
        for left,right in ((np.float32,np.float64),(np.float32,np.float32),(np.float64,np.float64)):
            for strided in (False,True):
                audio=rng.normal(0,.1,(2,4097)).astype(left)
                piano=rng.normal(0,.1,audio.shape).astype(right)
                audio[:,0]=-0.;piano[:,1]=0.
                if strided:audio=audio[:,::-1];piano=piano[:,::-1]
                original_audio,original_piano=audio.copy(),piano.copy()
                expected=np.stack((piano,audio-piano)).astype(np.float32)
                audio.setflags(write=False);piano.setflags(write=False)
                actual=piano_and_backing(audio,piano)
                self.assertEqual(actual.tobytes(),expected.tobytes())
                self.assertEqual(actual.dtype,np.float32)
                self.assertTrue(actual.flags.owndata and actual.flags.c_contiguous and actual.flags.writeable)
                self.assertFalse(np.shares_memory(actual,audio) or np.shares_memory(actual,piano))
                self.assertEqual(audio.tobytes(),original_audio.tobytes())
                self.assertEqual(piano.tobytes(),original_piano.tobytes())

    def test_mask_workspace_preserves_original_arithmetic_and_input_arrays(self):
        rng = np.random.default_rng(82)
        for left, right in ((np.float32,np.float32), (np.float64,np.float64), (np.float32,np.float64)):
            for strided in (False, True):
                with self.subTest(left=left, right=right, strided=strided):
                    spectrum = rng.normal(size=(31,43,2)).astype(left)
                    mask = rng.normal(size=spectrum.shape).astype(right)
                    spectrum[0] = 0;mask[1] = -0.
                    if strided:spectrum=spectrum[:,::-1];mask=mask[:,::-1]
                    original_spectrum, original_mask = spectrum.copy(), mask.copy()
                    a,b=spectrum[...,0],spectrum[...,1];c,d=mask[...,0],mask[...,1]
                    expected=np.stack((a*c-b*d,a*d+b*c),axis=-1)
                    actual=apply_complex_mask(spectrum,mask)
                    self.assertEqual(actual.dtype,expected.dtype)
                    self.assertEqual(actual.tobytes(),expected.tobytes())
                    self.assertEqual(spectrum.tobytes(),original_spectrum.tobytes())
                    self.assertEqual(mask.tobytes(),original_mask.tobytes())

    def test_model_receipt_imports_when_mac_app_is_a_standalone_entrypoint(self):
        namespace = runpy.run_path(str(Path(__file__).resolve().parents[1]/'music_studio/mac_app.py'))
        self.assertFalse(namespace['__package__'])
        from music_studio.native_piano_assets import HEAD
        from music_studio.piano_backend import selected_piano_backend
        identity = namespace['native_piano_identity']()
        self.assertEqual(identity['backend'], selected_piano_backend())
        self.assertEqual(identity['head_sha256'], HEAD['sha256'])
        from music_studio.mlx_piano_assets import WEIGHTS
        with patch('music_studio.piano_backend.sys.platform', 'darwin'), \
             patch('music_studio.piano_backend.platform.machine', return_value='arm64'), \
             patch.dict('os.environ', {}, clear=True):
            identity = namespace['native_piano_identity']()
        self.assertEqual(identity['backend'], 'mlx')
        self.assertEqual(identity['mlx_weights_sha256'], WEIGHTS['sha256'])
        with patch.dict('os.environ', {'BLAZE_PIANO_BACKEND':'onnx'}):
            identity = namespace['native_piano_identity']()
        self.assertEqual(identity['backend'], 'onnx')

    def test_piano_backend_defaults_to_metal_only_on_apple_silicon(self):
        from music_studio.piano_backend import selected_piano_backend
        with patch.dict('os.environ', {}, clear=True), \
             patch('music_studio.piano_backend.sys.platform', 'darwin'), \
             patch('music_studio.piano_backend.platform.machine', return_value='arm64'):
            self.assertEqual(selected_piano_backend(), 'mlx')
        with patch.dict('os.environ', {}, clear=True), \
             patch('music_studio.piano_backend.sys.platform', 'darwin'), \
             patch('music_studio.piano_backend.platform.machine', return_value='x86_64'):
            self.assertEqual(selected_piano_backend(), 'onnx')
        with patch.dict('os.environ', {'BLAZE_PIANO_BACKEND':'invalid'}):
            with self.assertRaisesRegex(ValueError, 'Choose mlx or onnx'):
                selected_piano_backend()

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
