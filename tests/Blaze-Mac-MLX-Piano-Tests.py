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
from music_studio.mlx_piano_model import PianoModel, validate_weights, weight_shapes, numpy_mask
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

    def test_independent_batches_stop_before_submitting_more_work_when_cancelled(self):
        model=PianoModel.__new__(PianoModel);model.mx=Mock();model.batch_tokens=12
        model._transformer_block=Mock(return_value=np.zeros((3,4,256)))
        check=Mock(side_effect=[None,SeparationCancelled('cancelled')])
        with self.assertRaises(SeparationCancelled):
            model.transformer(np.zeros((8,4,256)),'layer',check)
        model._transformer_block.assert_called_once()
        model.mx.concatenate.assert_not_called()

    def test_production_batches_bound_qkv_allocation_without_truncating_either_axis(self):
        model=PianoModel.__new__(PianoModel);model.mx=Mock();model.batch_tokens=32768
        model._transformer_block=Mock(side_effect=lambda value,*_:value)
        for batch,context in ((62,1723),(1723,62)):
            model._transformer_block.reset_mock()
            value=np.broadcast_to(np.arange(batch)[:,None,None],(batch,context,256))
            model.transformer(value,'layer',lambda:None)
            pieces=[call.args[0] for call in model._transformer_block.call_args_list]
            self.assertEqual(sum(piece.shape[0] for piece in pieces),batch)
            self.assertTrue(all(piece.shape[1]==context for piece in pieces))
            self.assertLessEqual(max(piece.shape[0]*context*1536*4 for piece in pieces),192*1024**2)
            np.testing.assert_array_equal(np.concatenate([piece[:,0,0] for piece in pieces]),np.arange(batch))

    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_independent_batches_preserve_full_attention_context_and_fp32_outputs(self):
        import mlx.core as mx
        rng=np.random.default_rng(184)
        model=PianoModel.__new__(PianoModel);model.mx=mx;model.gpu=False;model.rotary_cache={}
        arrays={
            'layer.0.norm.gamma':np.ones(256,np.float32),
            'layer.0.to_qkv.weight':rng.normal(0,.02,(1536,256)).astype(np.float32),
            'layer.0.to_gates.weight':rng.normal(0,.02,(8,256)).astype(np.float32),
            'layer.0.to_gates.bias':np.zeros(8,np.float32),
            'layer.0.to_out.0.weight':rng.normal(0,.02,(256,512)).astype(np.float32),
            'layer.0.rotary_embed.freqs':(10000**(-np.arange(0,64,2,dtype=np.float32)/64)).astype(np.float16).astype(np.float32),
            'layer.1.net.0.gamma':np.ones(256,np.float32),
            'layer.1.net.1.weight':rng.normal(0,.02,(1024,256)).astype(np.float32),
            'layer.1.net.1.bias':np.zeros(1024,np.float32),
            'layer.1.net.4.weight':rng.normal(0,.02,(256,1024)).astype(np.float32),
            'layer.1.net.4.bias':np.zeros(256,np.float32),
        }
        devices=(mx.cpu,mx.gpu) if mx.metal.is_available() else (mx.cpu,)
        for device in devices:
            model.gpu=device==mx.gpu
            with mx.stream(mx.new_stream(device)):
                model.weights={key:mx.array(value) for key,value in arrays.items()}
                model.feed_forward=mx.compile(model._feed_forward)
                for batch,context in ((7,129),(17,62)):
                    for scale in (1.,1e-15,0.):
                        value=mx.array(rng.normal(0,scale,(batch,context,256)).astype(np.float32))
                        original=np.array(value,copy=True)
                        expected=np.array(model._transformer_block(value,'layer',lambda:None))
                        model.batch_tokens=context*3
                        with patch.object(model,'_transformer_block',wraps=model._transformer_block) as block:
                            actual=np.array(model.transformer(value,'layer',lambda:None))
                        self.assertEqual(actual.dtype,np.float32)
                        # Different Metal GEMM batch shapes may change FP32
                        # accumulation rounding, especially near cancellation.
                        # Keep this below 1e-6 absolute; the full checkpoint
                        # comparison independently gates model output parity.
                        np.testing.assert_allclose(actual,expected,atol=8*np.finfo(np.float32).eps,rtol=1e-6)
                        np.testing.assert_array_equal(np.array(value),original)
                        self.assertTrue(all(call.args[0].shape[0]<=3 and call.args[0].shape[1]==context for call in block.call_args_list))

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
            model.rotary_cache = {}
            values = np.zeros((1,1,1025,64),dtype='float32');values[...,::2] = 1
            actual = np.array(model.rope(mx.array(values),'rotary'))
            angles = np.arange(1025,dtype='float32')[:,None]*frequencies[None,:]
            np.testing.assert_allclose(actual[0,0,:,::2],np.cos(angles),atol=1e-6)
            np.testing.assert_allclose(actual[0,0,:,1::2],np.sin(angles),atol=1e-6)
            paired = mx.stack((mx.array(values),mx.array(values)*.25))
            actual_pair = np.array(model.rope(paired,'rotary'))
            np.testing.assert_array_equal(actual_pair[0],actual)
            np.testing.assert_array_equal(actual_pair[1],actual*.25)
            first = model.rotary_cache['rotary']
            with patch('mlx.core.cos',side_effect=AssertionError('Repeated rotary cosine')), \
                 patch('mlx.core.sin',side_effect=AssertionError('Repeated rotary sine')):
                repeated=np.array(model.rope(mx.array(values),'rotary'))
            self.assertEqual(repeated.tobytes(),actual.tobytes())
            self.assertIs(model.rotary_cache['rotary'],first)
            # Context changes replace only this key; they never use a stale table.
            shorter=mx.array(values[:,:,:62])
            angles=mx.repeat(mx.arange(62,dtype=mx.float32)[:,None]*model.weights['rotary'][None,:],2,axis=-1)
            pairs=shorter.reshape(*shorter.shape[:-1],32,2)
            rotated=mx.stack((-pairs[...,1],pairs[...,0]),axis=-1).reshape(shorter.shape)
            reference=np.array(shorter*mx.cos(angles)+rotated*mx.sin(angles))
            changed=np.array(model.rope(shorter,'rotary'))
            self.assertEqual(changed.tobytes(),reference.tobytes())
            self.assertEqual(len(model.rotary_cache),1)
            self.assertEqual(model.rotary_cache['rotary'][0],62)
            model.weights['alternate']=model.weights['rotary']*.5
            alternate=np.array(model.rope(shorter,'alternate'))
            self.assertFalse(np.array_equal(alternate,changed))
            self.assertEqual(len(model.rotary_cache),2)
            self.assertEqual(np.array(model.rope(shorter,'rotary')).tobytes(),changed.tobytes())



    @unittest.skipUnless(importlib.util.find_spec('mlx'), 'MLX numeric reference requested in its environment')
    def test_numpy_mask_view_retains_owner_precision_and_values_after_cache_cleanup(self):
        import gc
        import mlx.core as mx
        from music_studio.native_piano import apply_complex_mask
        with mx.stream(mx.new_stream(mx.cpu)):
            rng=np.random.default_rng(175)
            value=mx.array(rng.normal(size=(1,1,37,41,2)).astype(np.float32)).transpose(0,1,3,2,4)
            mx.eval(value)
            original=np.array(value,copy=True);mask=numpy_mask(value)
            self.assertEqual(mask.dtype,original.dtype)
            self.assertEqual(mask.tobytes(),original.tobytes())
            self.assertFalse(mask.flags.owndata)
            self.assertFalse(mask.flags.writeable)
            with self.assertRaises(ValueError):mask[0,0,0,0,0]=0
            spectrum=rng.normal(size=mask.shape[2:]).astype(np.float32)
            expected=apply_complex_mask(spectrum,original[0,0])
            del value;gc.collect();mx.clear_cache()
            self.assertEqual(mask.tobytes(),original.tobytes())
            self.assertEqual(apply_complex_mask(spectrum,mask[0,0]).tobytes(),expected.tobytes())

    def test_close_releases_cached_rotary_tables(self):
        model=PianoModel.__new__(PianoModel);model.mx=Mock();model.stream=object()
        model.weights={'weight':object()};model.rotary_cache={'rotary':(1723,object(),object())}
        model.old_cache_limit=123;model.feed_forward=object()
        model.close()
        self.assertEqual(model.rotary_cache,{})
        self.assertEqual(model.weights,{})
        model.mx.clear_cache.assert_called_once()
        model.mx.set_cache_limit.assert_called_once_with(123)

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
