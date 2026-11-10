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
from music_studio.stems import _write_header
from tools.benchmark_macos_stems import compare_wavs
import numpy as np

SHA = 'a' * 64


class RuntimeTests(unittest.TestCase):
    def test_gpu_comparison_detects_drift_and_incompatible_duration(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'cpu.wav', Path(d)/'candidate.wav'
            values = np.full((140000, 2), .1, dtype='<f4')
            def write(path, samples):
                with path.open('wb') as stream:
                    _write_header(stream, len(samples));stream.write(samples.tobytes())
            write(a, values);write(b, values)
            self.assertEqual(compare_wavs(a, b)['rms_error'], 0)
            write(b, values*.5)
            self.assertAlmostEqual(compare_wavs(a, b)['normalized_rms_error'], .5)
            write(b, values[:1])
            with self.assertRaisesRegex(ValueError, 'durations'):
                compare_wavs(a, b)

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
            engine.runtime.session_from_file.side_effect = lambda *_, **__: (event.set(), session)[1]
            with self.assertRaises(SeparationCancelled):
                engine._graph(meta, np.zeros(1, dtype='float32'), event)
            engine.runtime.finish.assert_called_once_with(session)
            self.assertIsNone(engine.session)
            session.run.assert_not_called()
            engine.runtime.close.assert_called_once()

    def test_file_sessions_reuse_verified_graphs_only_within_one_job(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = StemRuntime(backend='cpu', cache=root/'cache', profile=root/'profiles')
            # Mock only the unavailable Core ML session constructor; exercise
            # the real cache, checksum, profile and release lifecycle.
            runtime.backend = 'coreml'
            sessions = []
            def create(*args, **kwargs):
                session = Mock()
                session.get_providers.return_value = ['CoreMLExecutionProvider']
                sessions.append(session)
                return session
            files = []
            for i in range(3):
                payload = bytes([i]) * 8
                path = root/f'{i}.onnx';path.write_bytes(payload)
                files.append((path, hashlib.sha256(payload).hexdigest(), len(payload)))
            with patch('music_studio.stem_runtime.ort.InferenceSession', side_effect=create), \
                 patch('music_studio.stem_runtime.SESSION_CACHE_BYTES', 16):
                for _ in range(3):
                    for path, sha, size in files:
                        session = runtime.session_from_file(path, Mock(), sha, size)
                        runtime.finish(session)
                self.assertEqual(len(sessions), 5)  # Two retained, third recreated.
                self.assertEqual(runtime._session_bytes, 16)
                for session in sessions[:2]:session.end_profiling.assert_not_called()
                runtime.close();runtime.close()
                self.assertFalse(runtime._pending)
                self.assertFalse(runtime._sessions)
                self.assertEqual(runtime._session_bytes, 0)
                for session in sessions:session.end_profiling.assert_called_once()
                self.assertEqual(sorted(r.get('session_reuses', 0) for r in runtime.records), [0, 0, 0, 2, 2])
                path, sha, size = files[0]
                path.write_bytes(b'tampered')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    runtime.session_from_file(path, Mock(), sha, size)
                self.assertEqual(len(sessions), 5)

    def test_file_cache_does_not_retain_oversized_sessions_or_change_cpu_policy(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'graph.onnx';path.write_bytes(b'verified')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            for backend in ('cpu', 'coreml'):
                runtime = StemRuntime(backend='cpu');runtime.backend = backend
                with patch.object(runtime, 'session', side_effect=lambda *args: Mock()) as create, \
                     patch('music_studio.stem_runtime.SESSION_CACHE_BYTES', 4):
                    for _ in range(2):
                        session = runtime.session_from_file(path, Mock(), sha, 8)
                        runtime.finish(session)
                    self.assertEqual(create.call_count, 2)
                    self.assertFalse(runtime._sessions)

    def test_cancel_after_checksum_does_not_start_model_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'graph.onnx';path.write_bytes(b'verified')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            runtime = StemRuntime(backend='cpu')
            check = Mock(side_effect=[None, SeparationCancelled('cancelled')])
            with patch.object(runtime, 'session') as create:
                with self.assertRaises(SeparationCancelled):
                    runtime.session_from_file(path, Mock(), sha, 8, check=check)
            create.assert_not_called()
            self.assertFalse(runtime._pending)

    def test_reused_real_onnx_session_preserves_distinct_chunk_results(self):
        import onnxruntime as ort
        from onnxruntime.datasets import get_example
        path = Path(get_example('mul_1.onnx'))
        data = path.read_bytes();sha = hashlib.sha256(data).hexdigest()
        runtime = StemRuntime(backend='cpu')
        runtime.backend = 'coreml'  # Exercise admission, not GPU performance.
        reference = ort.InferenceSession(data, providers=['CPUExecutionProvider'])
        def create(verified, options, model_sha):
            return ort.InferenceSession(verified, providers=['CPUExecutionProvider'])
        with patch.object(runtime, 'session', side_effect=create) as factory:
            for offset in (0, 10, -5):
                chunk = (np.arange(6,dtype='float32')+offset).reshape(3,2)
                session = runtime.session_from_file(path, ort.SessionOptions(), sha, len(data))
                np.testing.assert_array_equal(session.run(None, {'X':chunk})[0],
                                              reference.run(None, {'X':chunk})[0])
                runtime.finish(session)
            self.assertEqual(factory.call_count, 1)
            runtime.close()
            self.assertFalse(runtime._sessions)

    @unittest.skipUnless(sys.platform == 'darwin', 'Native Core ML check runs on macOS 26')
    def test_native_coreml_reuses_a_real_graph_and_finishes_its_profile(self):
        import onnxruntime as ort
        from onnxruntime.datasets import get_example
        path = Path(get_example('mul_1.onnx'))
        data = path.read_bytes();sha = hashlib.sha256(data).hexdigest()
        reference = ort.InferenceSession(data, providers=['CPUExecutionProvider'])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = StemRuntime(backend='coreml', cache=root/'cache', profile=root/'profiles')
            try:
                for offset in (0, 10, -5):
                    chunk = (np.arange(6,dtype='float32')+offset).reshape(3,2)
                    session = runtime.session_from_file(path, ort.SessionOptions(), sha, len(data))
                    np.testing.assert_array_equal(session.run(None, {'X':chunk})[0],
                                                  reference.run(None, {'X':chunk})[0])
                    runtime.finish(session)
            finally:
                runtime.close()
            self.assertFalse(runtime._sessions)
            self.assertFalse(runtime._pending)
            self.assertEqual(len(runtime.records), 1)
            self.assertEqual(runtime.records[0]['session_reuses'], 2)
            self.assertTrue(Path(runtime.records[0]['profile']).is_file())

    def test_cpu_override_does_not_create_gpu_cache(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'BLAZE_STEM_BACKEND':'cpu'}):
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
            self.assertEqual(options['RequireStaticInputShapes'], '0')
            self.assertEqual(options['EnableOnSubgraphs'], '1')
            self.assertEqual(Path(options['ModelCacheDirectory']).name, SHA)
            self.assertEqual(options['ProfileComputePlan'], '1')
            session.disable_fallback.assert_called_once()
            runtime.finish(session);session.end_profiling.assert_called_once()
            session.get_providers.return_value = ['CPUExecutionProvider']
            with patch('music_studio.stem_runtime.ort.InferenceSession', return_value=session):
                with self.assertRaisesRegex(ValueError, 'could not initialize'):
                    runtime.session(b'verified bytes', Mock(), SHA)

    def test_apple_silicon_defaults_to_coreml_when_provider_is_available(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('music_studio.stem_runtime.sys.platform', 'darwin'), \
             patch('music_studio.stem_runtime.platform.machine', return_value='arm64'), \
             patch('music_studio.stem_runtime.ort.__version__', '1.31.0'), \
             patch('music_studio.stem_runtime.ort.get_available_providers', return_value=['CoreMLExecutionProvider','CPUExecutionProvider']):
            self.assertEqual(StemRuntime().backend, 'coreml')

    def test_coreml_cache_separates_exact_frame_shapes(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('music_studio.stem_runtime.sys.platform', 'darwin'), \
             patch('music_studio.stem_runtime.platform.machine', return_value='arm64'), \
             patch('music_studio.stem_runtime.ort.__version__', '1.31.0'), \
             patch('music_studio.stem_runtime.ort.get_available_providers', return_value=['CoreMLExecutionProvider','CPUExecutionProvider']):
            runtime = StemRuntime(backend='coreml', cache=d)
            session = Mock();session.get_providers.return_value = ['CoreMLExecutionProvider','CPUExecutionProvider']
            directories = []
            with patch('music_studio.stem_runtime.ort.InferenceSession', return_value=session) as create:
                for frames in (220, 1500, 220):
                    options = Mock()
                    runtime.session(b'verified bytes', options, SHA, free_dimensions={'frames':frames})
                    options.add_free_dimension_override_by_name.assert_called_once_with('frames', frames)
                    settings = create.call_args.kwargs['providers'][0][1]
                    self.assertEqual(settings['RequireStaticInputShapes'], '1')
                    self.assertEqual(settings['MLComputeUnits'], 'CPUAndGPU')
                    directories.append(settings['ModelCacheDirectory'])
                    runtime.finish(session)
            self.assertNotEqual(directories[0], directories[1])
            self.assertEqual(directories[0], directories[2])

    def test_apple_silicon_does_not_silently_choose_cpu_without_coreml(self):
        with patch.dict('os.environ', {}, clear=True), \
             patch('music_studio.stem_runtime.sys.platform', 'darwin'), \
             patch('music_studio.stem_runtime.platform.machine', return_value='arm64'), \
             patch('music_studio.stem_runtime.ort.__version__', '1.31.0'), \
             patch('music_studio.stem_runtime.ort.get_available_providers', return_value=['CPUExecutionProvider']):
            with self.assertRaisesRegex(ValueError, 'Core ML GPU execution provider'):
                StemRuntime()

    def test_invalid_hash_and_unknown_backend_fail_before_execution(self):
        with self.assertRaises(ValueError):StemRuntime(backend='gpu-magic')
        with self.assertRaises(ValueError):StemRuntime(backend='cpu').session(b'bytes', Mock(), '../cache')


if __name__ == '__main__':
    unittest.main()
