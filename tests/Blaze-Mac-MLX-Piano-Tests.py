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
from music_studio.stems import SeparationCancelled
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

    def test_cancellation_after_attention_submission_stops_before_feed_forward(self):
        model = PianoModel.__new__(PianoModel);model.mx = Mock()
        model.attention = Mock(return_value=np.ones(4))
        model.norm = Mock()
        with self.assertRaises(SeparationCancelled):
            model.transformer(np.ones(4), 'layer', Mock(side_effect=SeparationCancelled('cancelled')))
        model.mx.async_eval.assert_called_once()
        model.mx.eval.assert_not_called()
        model.norm.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_async_transformer_matches_synchronous_math_without_flushing_buffers(self):
        import mlx.core as mx
        with mx.stream(mx.new_stream(mx.cpu)):
            model = PianoModel.__new__(PianoModel);model.mx = mx
            model.attention = lambda x, _: x*.125
            random = np.random.default_rng(18)
            arrays = {'layer.1.net.0.gamma':np.ones(4,dtype='float32'),
                      'layer.1.net.1.weight':random.normal(0,.1,(8,4)).astype('float32'),
                      'layer.1.net.1.bias':np.zeros(8,dtype='float32'),
                      'layer.1.net.4.weight':random.normal(0,.1,(4,8)).astype('float32'),
                      'layer.1.net.4.bias':np.zeros(4,dtype='float32')}
            model.weights = {key:mx.array(value) for key,value in arrays.items()}
            model.feed_forward = mx.compile(model._feed_forward)
            for scale in (.1, 1e-15, 0):
                x = mx.array(random.normal(0,scale,(2,4)).astype('float32'))
                expected = x+model.attention(x,'layer.0');mx.eval(expected)
                y = model.linear(model.norm(expected,'layer.1.net.0.gamma'),'layer.1.net.1')
                y = .5*y*(1+mx.erf(y/2**.5))
                expected = expected+model.linear(y,'layer.1.net.4');mx.eval(expected)
                with patch('mlx.core.clear_cache') as clear:
                    actual = model.transformer(x,'layer',lambda: None)
                np.testing.assert_allclose(np.array(actual),np.array(expected),atol=1e-7,rtol=1e-6)
                clear.assert_not_called()
            # A second layer must use its own parameters, not the first trace's.
            model.weights['layer.1.net.4.bias'] = mx.full((4,), .25)
            changed = np.array(model.transformer(mx.zeros((2,4)),'layer',lambda: None))
            np.testing.assert_allclose(changed,.25,atol=1e-7)

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
            paired = mx.stack((mx.array(values),mx.array(values)*.25))
            actual_pair = np.array(model.rope(paired,'rotary'))
            np.testing.assert_array_equal(actual_pair[0],actual)
            np.testing.assert_array_equal(actual_pair[1],actual*.25)

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
