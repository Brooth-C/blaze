"""CQT placement must preserve the original preprocessing, with neural GPU use."""
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import onnxruntime as ort
from music_studio.engine import ModelBundle
from music_studio.stem_runtime import StemRuntime
from music_studio.verified_session import VerifiedSession

ROOT = Path(__file__).resolve().parents[1]


class FrontendPlacement(unittest.TestCase):
    def test_cpu_preprocessing_keeps_neural_runtime_and_lazy_asset_checks(self):
        manifest = json.loads((ROOT / 'music_studio/models/manifest.json').read_text())
        for backend in ('cpu', 'coreml'):
            neural = SimpleNamespace(backend=backend)
            preprocessing = SimpleNamespace(backend='cpu')
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / 'manifest.json').write_text(json.dumps(manifest))
                with patch('music_studio.engine.StemRuntime', side_effect=[neural, preprocessing]) as factory, \
                     patch('music_studio.engine.VerifiedSession', side_effect=lambda *args: Mock(runtime=args[2])) as session:
                    bundle = ModelBundle(directory, 'extended')
            self.assertIs(bundle.runtime, neural)
            self.assertIs(bundle.network.runtime, neural)
            self.assertIs(bundle.frontend.runtime, preprocessing if backend == 'coreml' else neural)
            self.assertEqual(factory.call_count, 2 if backend == 'coreml' else 1)
            if backend == 'coreml':
                self.assertEqual(factory.call_args.kwargs, {'backend': 'cpu'})
            # Both paths still create checksum-verifying lazy assets; neither
            # bypasses verification nor executes a neural model at construction.
            self.assertEqual(session.call_count, 2)
            self.assertEqual(session.call_args_list[0].args[1], manifest['frontend'])
            self.assertEqual(session.call_args_list[1].args[1], manifest['models']['extended'])


@unittest.skipUnless(os.environ.get('BLAZE_CHORD_MODEL_DIR') and sys.platform == 'darwin'
                     and platform.machine().lower() in ('arm64', 'aarch64'),
                     'Actual CQT/Core ML parity requires the production assets on Apple Silicon macOS.')
class NativeFrontendParity(unittest.TestCase):
    def test_original_coreml_and_cpu_frontend_match_every_output_byte(self):
        directory = Path(os.environ['BLAZE_CHORD_MODEL_DIR'])
        manifest = json.loads((directory / 'manifest.json').read_text())
        expected = json.loads((ROOT / 'music_studio/models/manifest.json').read_text())['frontend']
        self.assertEqual(manifest['frontend'], expected)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        with tempfile.TemporaryDirectory() as cache:
            previous = VerifiedSession(directory, expected, StemRuntime(backend='coreml', cache=cache), options, 700 * 1024**2)
            bundle = ModelBundle(directory, 'extended')
            try:
                self.assertEqual(bundle.frontend.runtime.backend, 'cpu')
                self.assertEqual(bundle.network.runtime.backend, 'coreml')
                for length in (4410, 110593, 221184):
                    rng = np.random.default_rng(length)
                    normal = rng.normal(0, .1, length).astype(np.float32)
                    impulse = np.zeros(length, np.float32)
                    impulse[[0, length // 2, length - 1]] = [1, -1, 1]
                    harmonic = (.1 * np.sin(np.arange(length) * 2 * np.pi * 220 / 22050)).astype(np.float32)
                    for signal in (normal, normal * np.float32(1e-5), np.zeros(length, np.float32), impulse, harmonic):
                        signal.setflags(write=False)
                        wanted = previous.run(None, {'pcm': signal[None]})[0]
                        actual = bundle.frontend.run(None, {'pcm': signal[None]})[0]
                        self.assertEqual(actual.shape, wanted.shape)
                        self.assertEqual(actual.dtype, wanted.dtype)
                        self.assertEqual(actual.tobytes(), wanted.tobytes())
                print('Production CQT: CPU and original Core ML outputs byte-identical across 15 cases.', flush=True)
            finally:
                previous.close()
                bundle.close()


if __name__ == '__main__':
    unittest.main()
