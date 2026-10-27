"""torch.stft / torch.istft reimplemented in numpy, bit-for-bit in intent.

The RoFormer graphs are exported without their STFT ends (ONNX has neither
`istft` nor a complex dtype), so the caller owns the transform. These two
functions are the exact configuration the reference uses: periodic Hann,
`center=True` with reflect padding, `normalized=False`, one-sided.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache(maxsize=8)
def hann_periodic(win_length: int) -> np.ndarray:
    """torch.hann_window(win_length, periodic=True)."""
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(win_length) / win_length))


def stft(audio: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    """[C, N] real -> [C, n_fft//2+1, T] complex, T = N // hop_length + 1."""
    window = hann_periodic(n_fft)
    padded = np.pad(audio, ((0, 0), (n_fft // 2, n_fft // 2)), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft, axis=1)[:, ::hop_length, :]
    spec = np.fft.rfft(frames * window, axis=2)
    return np.ascontiguousarray(spec.transpose(0, 2, 1))


def _overlap_add(frames: np.ndarray, hop_length: int, out_length: int) -> np.ndarray:
    """frames [n_fft, T] -> signal [out_length], summed at hop stride."""
    n_fft, n_frames = frames.shape
    signal = np.zeros(out_length)
    for t in range(n_frames):
        start = t * hop_length
        signal[start : start + n_fft] += frames[:, t]
    return signal


def istft(spec: np.ndarray, n_fft: int, hop_length: int, length: int) -> np.ndarray:
    """[n_fft//2+1, T] complex -> [length] real (WOLA, center padding removed)."""
    window = hann_periodic(n_fft)
    n_frames = spec.shape[1]
    expected = n_fft + hop_length * (n_frames - 1)
    frames = np.fft.irfft(spec, n=n_fft, axis=0) * window[:, None]
    signal = _overlap_add(frames, hop_length, expected)
    envelope = _overlap_add(
        np.repeat((window**2)[:, None], n_frames, axis=1), hop_length, expected
    )
    # Slice BEFORE dividing: the first and last n_fft/2 samples have partial
    # window coverage (the envelope is exactly 0 at sample 0 for a periodic
    # Hann), and those are precisely the samples `center=True` throws away.
    start = n_fft // 2
    stop = min(start + length, expected)
    out = signal[start:stop] / envelope[start:stop]
    if out.size < length:  # torch zero-pads when `length` runs past the signal
        out = np.pad(out, (0, length - out.size))
    return out


def stft_bands_last(audio: np.ndarray, n_fft: int, hop_length: int) -> np.ndarray:
    """[C, N] -> [1, (F*C), T, 2] float32 -- the graph's `spec` input layout.

    Mirrors the reference's `rearrange(spec, 'b s f t c -> b (f s) t c')`:
    channel is the FASTEST-varying axis, interleaved inside frequency.
    """
    spec = stft(audio, n_fft, hop_length)  # [C, F, T]
    real = np.stack([spec.real, spec.imag], axis=-1)  # [C, F, T, 2]
    interleaved = real.transpose(1, 0, 2, 3)  # [F, C, T, 2]
    flat = interleaved.reshape(-1, spec.shape[2], 2)  # [(F C), T, 2]
    return np.ascontiguousarray(flat[None].astype(np.float32))


def istft_bands_last(
    spec: np.ndarray, channels: int, n_fft: int, hop_length: int, length: int
) -> np.ndarray:
    """[(F*C), T, 2] float -> [C, length] real. Inverse of `stft_bands_last`."""
    n_freqs = spec.shape[0] // channels
    per_channel = spec.reshape(n_freqs, channels, spec.shape[1], 2).transpose(1, 0, 2, 3)
    complex_spec = per_channel[..., 0] + 1j * per_channel[..., 1]
    return np.stack(
        [istft(complex_spec[c], n_fft, hop_length, length) for c in range(channels)]
    )
