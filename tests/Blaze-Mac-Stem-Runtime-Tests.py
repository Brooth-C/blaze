"""Provider selection, versioned caches and honest GPU evaluation failures."""
from pathlib import Path
import hashlib
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.stem_runtime import StemRuntime
from music_studio.roformer import RoformerSeparator
from music_studio.stems import SeparationCancelled
import numpy as np

SHA = 'a' * 64


class RuntimeTests(unittest.TestCase):
    def test_cancel_during_session_creation_releases_the_session(self):
        payload = b'controlled graph'
        meta = {'file': 'graph.onnx', 'bytes': len(payload),
                'sha256': hashlib.sha256(payload).hexdigest(), 'input_shape': [1], 'output_shape': [1]}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);(root/meta['file']).write_bytes(payload)
            event = threading.Event();session = Mock()
            session.get_inputs.return_value = [Mock(name='x', shape=[1], type='tensor(float)')]
            session.get_outputs.return_value = [Mock(name='y', shape=[1], type='tensor(float)')]
            # Mock's name constructor argument isn't its public .name value.
            session.get_inputs.return_value[0].name = 'x';session.get_outputs.return_value[0].name = 'y'
            engine = RoformerSeparator();engine.directory = root;engine.runtime = Mock()
            engine.runtime.session.side_effect = lambda *_: (event.set(), session)[1]
            with self.assertRaises(SeparationCancelled):
                engine._graph(meta, np.zeros(1, dtype='float32'), event)
            engine.runtime.finish.assert_called_once_with(session)
            self.assertIsNone(engine.session)
            session.run.assert_not_called()

    def test_cpu_default_does_not_create_gpu_cache(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {}, clear=True):
            runtime = StemRuntime(cache=Path(d)/'cache')
            session = Mock(); session.get_providers.return_value = ['CPUExecutionProvider']
            with patch('music_studio.stem_runtime.ort.InferenceSession', return_value=session) as create:
                self.assertIs(runtime.session(b'verified bytes', Mock(), SHA), session)
            self.assertEqual(create.call_args.kwargs['providers'], ['CPUExecutionProvider'])
            self.assertFalse((Path(d)/'cache').exists())
            runtime.finish(session);runtime.finish(session)
            self.assertEqual(len(runtime.records), 1)
            session.disable_fallback.assert_not_called()

    def test_unsupported_platform_or_old_runtime_fails_explicitly(self):
        with patch('music_studio.stem_runtime.sys.platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'Apple Silicon'):
                StemRuntime(backend='coreml')
        with patch('music_studio.stem_runtime.sys.platform', 'darwin'), patch('music_studio.stem_runtime.platform.machine', return_value='arm64'), patch('music_studio.stem_runtime.ort.__version__', '1.20.1'):
            with self.assertRaisesRegex(ValueError, '1.31'):
                StemRuntime(backend='coreml')

    def test_coreml_cache_identity_and_no_disguised_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch('music_studio.stem_runtime.sys.platform', 'darwin'), patch('music_studio.stem_runtime.platform.machine', return_value='arm64'), patch('music_studio.stem_runtime.ort.__version__', '1.31.0'), patch('music_studio.stem_runtime.ort.get_available_providers', return_value=['CoreMLExecutionProvider','CPUExecutionProvider']):
            runtime = StemRuntime(backend='coreml', cache=d, profile=Path(d)/'profiles')
            session = Mock();session.get_providers.return_value = ['CoreMLExecutionProvider','CPUExecutionProvider']
            with patch('music_studio.stem_runtime.ort.InferenceSession', return_value=session) as create:
                runtime.session(b'verified bytes', Mock(), SHA)
            provider, options = create.call_args.kwargs['providers'][0]
            self.assertEqual(provider, 'CoreMLExecutionProvider')
            self.assertEqual(options['MLComputeUnits'], 'CPUAndGPU')
            self.assertEqual(options['EnableOnSubgraphs'], '1')
            self.assertEqual(Path(options['ModelCacheDirectory']).name, SHA)
            self.assertEqual(options['ProfileComputePlan'], '1')
            session.disable_fallback.assert_called_once()
            runtime.finish(session);session.end_profiling.assert_called_once()
            session.get_providers.return_value = ['CPUExecutionProvider']
            with patch('music_studio.stem_runtime.ort.InferenceSession', return_value=session):
                with self.assertRaisesRegex(ValueError, 'could not initialize'):
                    runtime.session(b'verified bytes', Mock(), SHA)

    def test_invalid_hash_and_unknown_backend_fail_before_execution(self):
        with self.assertRaises(ValueError):StemRuntime(backend='gpu-magic')
        with self.assertRaises(ValueError):StemRuntime(backend='cpu').session(b'bytes', Mock(), '../cache')


if __name__ == '__main__':
    unittest.main()
