"""Beat This exact-shape execution and Core ML/CPU checkpoint parity."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from music_studio.rhythm import RhythmDetector
from music_studio.stem_runtime import StemRuntime


class RhythmSessions(unittest.TestCase):
    def test_exact_chunks_reuse_one_session_and_release_changed_shapes(self):
        detector = RhythmDetector.__new__(RhythmDetector)
        detector.runtime = Mock(backend='coreml')
        detector.network = None
        detector.network_frames = None
        detector.manifest = {'network':{'sha256':'a'*64}}
        detector._asset = Mock(return_value=b'verified graph')
        first, second = Mock(), Mock()
        detector.runtime.session.side_effect = [first, second]
        chunk = np.random.default_rng(7).normal(size=(220, 128)).astype('float32')
        detector._predict(chunk)
        detector._predict(chunk)
        self.assertEqual(detector.runtime.session.call_count, 1)
        np.testing.assert_array_equal(first.run.call_args.args[1]['spect'], chunk[None])
        detector._predict(chunk[:201])
        detector.runtime.finish.assert_any_call(first)
        self.assertEqual(detector.runtime.session.call_args.kwargs['free_dimensions'], {'frames':201})
        detector.close()
        detector.runtime.finish.assert_called_with(second)
        self.assertIsNone(detector.network)


@unittest.skipUnless(os.environ.get('BLAZE_RHYTHM_MODEL_DIR'), 'Set BLAZE_RHYTHM_MODEL_DIR for actual checkpoint parity.')
class RealRhythmModel(unittest.TestCase):
    def test_exact_frame_sessions_match_dynamic_cpu_checkpoint(self):
        directory = Path(os.environ['BLAZE_RHYTHM_MODEL_DIR'])
        manifest = json.loads((directory/'rhythm_manifest.json').read_text())
        data = (directory/manifest['network']['file']).read_bytes()
        model_sha = hashlib.sha256(data).hexdigest()
        self.assertEqual(model_sha, manifest['network']['sha256'])
        options = ort.SessionOptions();options.intra_op_num_threads = 2
        reference = ort.InferenceSession(data, sess_options=options, providers=['CPUExecutionProvider'])
        with tempfile.TemporaryDirectory() as cache:
            runtime = StemRuntime(cache=cache)
            detector = RhythmDetector(directory) if runtime.backend == 'coreml' else None
            if detector:
                detector.runtime = runtime
            for frames in (201, 600, 1500):
                with self.subTest(frames=frames):
                    value = np.random.default_rng(frames).uniform(0, 7, (1, frames, 128)).astype('float32')
                    wanted = reference.run(None, {'spect':value})
                    options = ort.SessionOptions();options.intra_op_num_threads = 2
                    if detector:
                        actual = detector._predict(value[0])
                        network = detector.network
                    else:
                        network = runtime.session(data, options, model_sha, free_dimensions={'frames':frames})
                        actual = network.run(None, {'spect':value})
                    try:
                        self.assertEqual(network.get_inputs()[0].shape, [1, frames, 128])
                        error = max(float(np.max(np.abs(a-b))) for a, b in zip(actual, wanted))
                        print(json.dumps({'backend':runtime.backend, 'frames':frames, 'max_abs_error':error}), flush=True)
                        self.assertLess(error, .003 if runtime.backend == 'coreml' else 1e-4)
                        for output in actual:
                            self.assertEqual(output.shape, (1, frames))
                            self.assertTrue(np.isfinite(output).all())
                    finally:
                        if detector:
                            detector.close()
                        else:
                            runtime.finish(network)
                    record = runtime.records[-1]
                    if runtime.backend == 'coreml' and runtime.profile:
                        events = json.loads(Path(record['profile']).read_text())
                        self.assertTrue(any(event.get('args', {}).get('provider') == 'CoreMLExecutionProvider'
                                            for event in events), 'No Core ML partition executed.')


if __name__ == '__main__':
    unittest.main()
