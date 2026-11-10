"""Narrow FP32 Mega53 piano evaluator, using fused Metal attention.

Same parameter names and math as the reviewed MIT MSST architecture. No stock
loader, model discovery, random parameters, shorter context or precision change.
Spectral transforms and streaming remain owned by NativePianoSeparator.
"""
import math
import numpy as np

BANDS = (2,)*24 + (4,)*12 + (12,)*8 + (24,)*8 + (48,)*8 + (128, 129)


def weight_shapes():
    shapes = {'final_norm.gamma': (256,)}
    for i, frequency in enumerate(BANDS):
        n = frequency*4
        p = f'band_split.to_features.{i}'
        shapes.update({p+'.0.gamma': (n,), p+'.1.weight': (256, n), p+'.1.bias': (256,)})
        p = f'mask_estimators.0.to_freqs.{i}.0'
        shapes.update({p+'.0.weight': (512, 256), p+'.0.bias': (512,),
                       p+'.2.weight': (n*2, 512), p+'.2.bias': (n*2,)})
    for block in range(12):
        for axis in range(2):
            p = f'layers.{block}.{axis}.layers.0'
            shapes.update({p+'.0.rotary_embed.freqs': (32,), p+'.0.norm.gamma': (256,),
                           p+'.0.to_qkv.weight': (1536, 256), p+'.0.to_gates.weight': (8, 256),
                           p+'.0.to_gates.bias': (8,), p+'.0.to_out.0.weight': (256, 512),
                           p+'.1.net.0.gamma': (256,), p+'.1.net.1.weight': (1024, 256),
                           p+'.1.net.1.bias': (1024,), p+'.1.net.4.weight': (256, 1024),
                           p+'.1.net.4.bias': (256,)})
    return shapes


def validate_weights(weights):
    expected = weight_shapes()
    if set(weights) != set(expected):
        raise ValueError('The MLX piano parameter set is incomplete or incompatible.')
    for key, shape in expected.items():
        if tuple(weights[key].shape) != shape or str(weights[key].dtype) not in ('float32', 'mlx.core.float32'):
            raise ValueError('The MLX piano parameter shape or precision is invalid: ' + key)


class PianoModel:
    def __init__(self, path, *, require_gpu=True):
        import mlx.core as mx
        self.mx = mx
        self.gpu = require_gpu
        if require_gpu and not mx.metal.is_available():
            raise ValueError('A Metal GPU is required for the MLX piano backend.')
        self.stream = mx.new_stream(mx.gpu if require_gpu else mx.cpu)
        # Cached free buffers are bounded; this is not a hard process-RSS cap.
        self.old_cache_limit = mx.set_cache_limit(256*1024**2)
        try:
            with mx.stream(self.stream):
                self.weights = mx.load(str(path))
                validate_weights(self.weights)
                mx.eval(*self.weights.values())
        except Exception:
            mx.clear_cache();mx.set_cache_limit(self.old_cache_limit)
            raise

    def norm(self, x, key):
        mx = self.mx
        # Original F.normalize clamps the L2 norm, rather than adding epsilon
        # inside a mean square. Preserve that behavior, including quiet inputs.
        length = mx.sqrt(mx.sum(x*x, axis=-1, keepdims=True))
        return x/mx.maximum(length, 1e-12)*math.sqrt(x.shape[-1])*self.weights[key]

    def linear(self, x, key, bias=True):
        y = x @ self.weights[key+'.weight'].T
        return y+self.weights[key+'.bias'] if bias else y

    def rope(self, x, key):
        mx = self.mx
        # The checkpoint's frequency values were stored in FP16. Loading them
        # into FP32 preserves those values; recomputing ideal base10000 does not.
        angles = mx.arange(x.shape[-2], dtype=mx.float32)[:, None]*self.weights[key][None, :]
        angles = mx.repeat(angles, 2, axis=-1)
        pairs = x.reshape(*x.shape[:-1], 32, 2)
        rotated = mx.stack((-pairs[..., 1], pairs[..., 0]), axis=-1).reshape(x.shape)
        return x*mx.cos(angles)+rotated*mx.sin(angles)

    def attention(self, x, key):
        mx = self.mx
        b, n, _ = x.shape
        normalized = self.norm(x, key+'.norm.gamma')
        qkv = self.linear(normalized, key+'.to_qkv', False).reshape(b, n, 3, 8, 64).transpose(2, 0, 3, 1, 4)
        # Rotate Q and K together instead of building identical trig graphs.
        qk = self.rope(qkv[:2], key+'.rotary_embed.freqs')
        q, k = qk[0], qk[1]
        v = qkv[2]
        if self.gpu:
            # Fail if a fused kernel is unavailable. Never silently allocate
            # the full context-squared attention matrix on an 8 GB target.
            out = mx.fast.scaled_dot_product_attention(q, k, v, scale=.125, force_fused=True)
        else:
            # Reference-only CPU execution, with the same four-item bound as
            # the original ONNX export. It is not a user-facing GPU fallback.
            pieces = []
            for offset in range(0, b, 4):
                scores = (q[offset:offset+4] @ k[offset:offset+4].swapaxes(-1, -2))*.125
                piece = mx.softmax(scores, axis=-1) @ v[offset:offset+4]
                mx.eval(piece);pieces.append(piece)
            out = mx.concatenate(pieces, axis=0)
        gates = mx.sigmoid(self.linear(normalized, key+'.to_gates')).transpose(0, 2, 1)[..., None]
        out = (out*gates).transpose(0, 2, 1, 3).reshape(b, n, 512)
        return self.linear(out, key+'.to_out.0', False)

    def transformer(self, x, prefix, check):
        mx = self.mx
        x = x+self.attention(x, prefix+'.0')
        # Submit attention without blocking Python before the feed-forward work.
        mx.async_eval(x);check()
        y = self.linear(self.norm(x, prefix+'.1.net.0.gamma'), prefix+'.1.net.1')
        y = .5*y*(1+mx.erf(y/math.sqrt(2)))
        x = x+self.linear(y, prefix+'.1.net.4')
        mx.eval(x);check()
        # Reuse buffers under the existing 256 MiB cache limit until close().
        return x

    def predict(self, spectrum, check=lambda: None, progress=lambda fraction: None):
        mx = self.mx
        if spectrum.dtype != np.float32 or spectrum.ndim != 4 or spectrum.shape[0] != 1 or spectrum.shape[1] != 2050 or spectrum.shape[3] != 2:
            raise ValueError('The MLX piano spectral input is incompatible.')
        with mx.stream(self.stream):
            check()
            t = spectrum.shape[2]
            flat = mx.array(spectrum).transpose(0, 2, 1, 3).reshape(1, t, 4100)
            bands, offset = [], 0
            for i, frequency in enumerate(BANDS):
                n = frequency*4;p = f'band_split.to_features.{i}'
                bands.append(self.linear(self.norm(flat[..., offset:offset+n], p+'.0.gamma'), p+'.1'))
                offset += n
            x = mx.stack(bands, axis=-2)
            mx.eval(x);check();del bands, flat
            for block in range(12):
                y = x.transpose(0, 2, 1, 3).reshape(62, t, 256)
                y = self.transformer(y, f'layers.{block}.0.layers.0', check)
                x = y.reshape(1, 62, t, 256).transpose(0, 2, 1, 3)
                y = x.reshape(t, 62, 256)
                y = self.transformer(y, f'layers.{block}.1.layers.0', check)
                x = y.reshape(1, t, 62, 256)
                progress((block+1)/13)
            x = self.norm(x, 'final_norm.gamma')
            masks = []
            for i in range(62):
                p = f'mask_estimators.0.to_freqs.{i}.0'
                y = mx.tanh(self.linear(x[:, :, i], p+'.0'))
                y = self.linear(y, p+'.2')
                a, b = mx.split(y, 2, axis=-1)
                masks.append(a*mx.sigmoid(b))
            result = mx.concatenate(masks, axis=-1).reshape(1, 1, t, 2050, 2).transpose(0, 1, 3, 2, 4)
            mx.eval(result);check();progress(1)
            return np.array(result, copy=True)

    def close(self):
        try:
            self.mx.synchronize(self.stream)
        finally:
            try:
                self.weights.clear()
            finally:
                try:
                    self.mx.clear_cache()
                finally:
                    self.mx.set_cache_limit(self.old_cache_limit)
