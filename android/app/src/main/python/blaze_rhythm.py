"""NumPy-only, streamed Beat This! frontend, matching the Windows implementation.

The neural network runs through Android ONNX Runtime in Java. Temporary features
remain in app-private storage and are deleted by the Java caller on every exit.
"""
import io
import json
import os
import numpy as np


def prepare_rhythm(pcm_path, frontend_bytes, feature_path, samples, cancel_check=None):
    with np.load(io.BytesIO(bytes(frontend_bytes)), allow_pickle=False) as assets:
        window = assets['window'].copy()
        filters = assets['filter'].copy()
    if window.shape != (1024,) or filters.shape != (513, 128):
        raise ValueError('Invalid rhythm frontend.')
    if os.path.getsize(pcm_path) != int(samples) * 4:
        raise ValueError('Incomplete decoded audio.')
    pending = np.empty(0, dtype=np.float32)
    tail = np.empty(0, dtype=np.float32)
    initial = True
    audible = False
    written = 0
    maximum = int(samples) // 441 + 1

    def extract(output, pending, written):
        if len(pending) < 1024:
            return pending, written
        frames = np.lib.stride_tricks.sliding_window_view(pending, 1024)[::441]
        magnitude = (np.abs(np.fft.rfft(frames * window, axis=1)) / 32).astype(np.float32)
        features = np.log1p(1000 * (magnitude @ filters)).astype('<f4')
        accepted = min(len(features), maximum - written)
        output.write(features[:accepted].tobytes())
        return pending[len(frames) * 441:].copy(), written + accepted

    with open(pcm_path, 'rb') as pcm, open(feature_path, 'wb') as output:
        while True:
            if cancel_check is not None:
                cancel_check.run()
            raw = pcm.read(16384 * 4)
            if not raw:
                break
            block = np.frombuffer(raw, dtype='<f4')
            if not np.isfinite(block).all():
                raise ValueError('Invalid decoded audio.')
            audible |= float(np.max(np.abs(block), initial=0)) > 1e-5
            tail = np.concatenate((tail, block))[-513:].copy()
            pending = np.concatenate((pending, block))
            if initial:
                if len(pending) < 513:
                    continue
                pending = np.concatenate((pending[1:513][::-1], pending))
                initial = False
            pending, written = extract(output, pending, written)
        if not initial:
            pending = np.concatenate((pending, tail[-2::-1]))
            pending, written = extract(output, pending, written)
    return json.dumps({'frames': written, 'audible': bool(audible)})


def rhythm_chunk(feature_path, frames, start):
    """Use the upstream six-frame overlap and short-file padding exactly."""
    frames, start = int(frames), int(start)
    if frames < 1 or os.path.getsize(feature_path) != frames * 128 * 4:
        raise ValueError('Incomplete rhythm features.')
    spect = np.memmap(feature_path, dtype='<f4', mode='r', shape=(frames, 128))
    left, right = max(start, 0), min(start + 1500, frames)
    chunk = np.asarray(spect[left:right])
    chunk = np.pad(chunk, ((max(0, -start), max(0, min(6, start + 1500 - frames))), (0, 0)))
    result = chunk.astype('<f4', copy=False).tobytes()
    del spect
    return result
