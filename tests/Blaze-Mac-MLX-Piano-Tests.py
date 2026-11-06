"""Strict parameter contracts and source-preserving fused-piano ownership."""
import importlib.util
import hashlib
import json
import tempfile
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.mlx_piano_model import PianoModel, validate_weights, weight_shapes
from music_studio.mlx_piano import MlxPianoSeparator


class MlxTests(unittest.TestCase):
    def test_incomplete_extra_or_reduced_precision_weights_are_never_accepted(self):
        weights = {k: SimpleNamespace(shape=s,dtype='float32') for k,s in weight_shapes().items()}
        validate_weights(weights)
        key = 'mask_estimators.0.to_freqs.0.0.0.weight'
        original = weights.pop(key)
        with self.assertRaisesRegex(ValueError,'parameter set'):validate_weights(weights)
        weights[key] = original;weights['unreviewed'] = original
        with self.assertRaisesRegex(ValueError,'parameter set'):validate_weights(weights)
        del weights['unreviewed'];weights[key] = SimpleNamespace(shape=original.shape,dtype='float16')
        with self.assertRaisesRegex(ValueError,'precision'):validate_weights(weights)

    def test_failed_job_releases_the_loaded_gpu_model(self):
        engine = MlxPianoSeparator();model = Mock();engine.model = model
        with patch('music_studio.native_piano.NativePianoSeparator.separate',side_effect=ValueError('Controlled failure')):
            with self.assertRaisesRegex(ValueError,'Controlled failure'):engine.separate('input','output')
        model.close.assert_called_once();self.assertIsNone(engine.model)

    def test_mlx_load_uses_only_its_pinned_weights(self):
        payload = b'pinned model fixture'
        weights = {'file':'fixture.safetensors','bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
        identity = {'weights':weights}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);assets = root/'mlx-piano';assets.mkdir()
            (assets/weights['file']).write_bytes(payload)
            (assets/'manifest.json').write_text(json.dumps(identity))
            engine = MlxPianoSeparator.__new__(MlxPianoSeparator)
            engine.mlx_directory = assets;engine.model = None
            loaded = Mock()
            with patch('music_studio.mlx_piano.WEIGHTS',weights), \
                 patch('music_studio.mlx_piano.manifest',return_value=identity), \
                 patch('music_studio.native_piano.NativePianoSeparator._load',side_effect=AssertionError('MLX must not load the ONNX model set')), \
                 patch('music_studio.mlx_piano_model.PianoModel',return_value=loaded) as model_factory:
                engine._load(__import__('threading').Event())
            self.assertIs(engine.model,loaded)
            model_factory.assert_called_once_with(assets/weights['file'])
            loaded.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_rope_retains_the_original_rounded_frequencies(self):
        import mlx.core as mx
        with mx.stream(mx.new_stream(mx.cpu)):
            model = PianoModel.__new__(PianoModel);model.mx = mx
            frequencies = (10000**(-np.arange(0,64,2,dtype='float32')/64)).astype('float16').astype('float32')
            model.weights = {'rotary':mx.array(frequencies)}
            values = np.zeros((1,1,1025,64),dtype='float32');values[...,::2] = 1
            actual = np.array(model.rope(mx.array(values),'rotary'))
            angles = np.arange(1025,dtype='float32')[:,None]*frequencies[None,:]
            np.testing.assert_allclose(actual[0,0,:,::2],np.cos(angles),atol=1e-6)
            np.testing.assert_allclose(actual[0,0,:,1::2],np.sin(angles),atol=1e-6)

    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_norm_preserves_original_quiet_input_epsilon(self):
        import mlx.core as mx
        with mx.stream(mx.new_stream(mx.cpu)):
            model = PianoModel.__new__(PianoModel);model.mx = mx;model.weights = {'norm':mx.ones(4)}
            result = np.array(model.norm(mx.full((1,4),1e-15),'norm'))
            np.testing.assert_allclose(result,np.full((1,4),.002),atol=1e-8)

    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_requested_gpu_does_not_fall_back_to_cpu_or_random_weights(self):
        with patch('mlx.core.metal.is_available',return_value=False):
            with self.assertRaisesRegex(ValueError,'Metal GPU'):PianoModel('missing.safetensors')


if __name__ == '__main__':unittest.main()
