"""Android's file-backed frontend and binary ORT bridge parity checks."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'android/app/src/main/python'))
from music_studio.lv_frontend import PortableLVFrontend  # noqa: E402
from blaze_harmony import Harmony, HEAD_COLUMNS  # noqa: E402

MODELS = ROOT / 'music_studio/models'
ASSET = MODELS / 'lv_cqt.npz'


class Callback:
    def __init__(self, fail_after=None):
        self.calls = 0
        self.fail_after = fail_after

    def run(self):
        self.calls += 1
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise InterruptedError('Cancelled')


class AndroidHarmonyTests(unittest.TestCase):
    def test_shared_source_is_exact(self):
        copied = ROOT / 'android/app/src/main/python/blaze_studio_shared'
        hashes = json.loads((copied / 'source-hashes.json').read_text(encoding='utf-8'))
        for name, expected in hashes.items():
            self.assertEqual(hashlib.sha256((ROOT / 'music_studio' / name).read_bytes()).hexdigest(), expected)
            self.assertEqual((ROOT / 'music_studio' / name).read_bytes(), (copied / name).read_bytes())
        # Loading the Android decoder has no Python ORT dependency.
        self.assertNotIn('onnxruntime', importlib.util.find_spec('blaze_studio_shared.structured').loader.get_source('blaze_studio_shared.structured').split('class StructuredRecognizer')[0])

    @unittest.skipUnless(ASSET.is_file(), 'Exported frontend asset is supplied by the build staging step.')
    def test_mapped_frontend_matches_windows(self):
        t = np.arange(22050 * 5, dtype=np.float64) / 22050
        pcm = sum(.12 * np.sin(2 * np.pi * frequency * t) for frequency in (261.63, 329.63, 392, 466.16, 587.33)).astype(np.float32)
        pcm[-3000:] = 0
        reference = PortableLVFrontend(ASSET)
        expected = reference.extract(pcm)
        with tempfile.TemporaryDirectory() as folder:
            callback = Callback()
            mapped = PortableLVFrontend(ASSET)
            actual = mapped.extract(pcm, output_path=Path(folder) / 'cqt.f32', check=callback.run)
            self.assertIsInstance(actual, np.memmap)
            self.assertEqual(actual.shape, expected.shape)
            self.assertEqual(mapped.last_tuning, reference.last_tuning)
            np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-6)
            self.assertGreater(callback.calls, 10)
            del actual

    @unittest.skipUnless(ASSET.is_file(), 'Exported frontend asset is supplied by the build staging step.')
    def test_frontend_cancellation_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(InterruptedError):
                PortableLVFrontend(ASSET).extract(np.ones(22050 * 6, np.float32), output_path=Path(folder) / 'cqt.f32', check=Callback(4).run)

    @unittest.skipUnless(ASSET.is_file(), 'Exported frontend asset is supplied by the build staging step.')
    def test_binary_heads_have_exact_shapes_and_context_weighting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            pcm = np.zeros(22050, np.float32)
            pcm.tofile(path / 'audio.f32')
            bridge = Harmony(str(MODELS), str(path), str(path / 'audio.f32'), len(pcm), Callback())
            frames = json.loads(bridge.prepare())['frames']
            values = [np.full((frames, columns), 1 / columns, np.float32) for columns in HEAD_COLUMNS]
            np.concatenate([value.ravel() for value in values]).astype('<f4').tofile(path / 'votes.f32')
            bridge.accumulate(str(path / 'votes.f32'), 0, frames)
            weight = np.minimum(np.minimum(np.arange(frames) + 1, np.arange(frames, 0, -1)), 129) / 129
            for actual, expected in zip(bridge.heads, values):
                np.testing.assert_allclose(actual, expected * weight[:, None], rtol=1e-7, atol=1e-8)
            with self.assertRaises(ValueError):
                bridge.accumulate(str(path / 'votes.f32'), -1, frames)
            bridge.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
