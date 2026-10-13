"""Portable LV-Chordia hybrid CQT and a reproducible asset/parity builder.

Runtime: NumPy only.  Build/verification: librosa 0.10.2.post1 + python-soxr.
The CQT/pitch routines below adapt the algorithms in librosa (ISC license);
distribution must retain librosa's copyright/license notice. The HQ impulse
response is generated build output; neither Soxr nor librosa is imported by
the runtime frontend. No model training is performed.
"""
# Adapted from librosa 0.10.2.post1 (ISC).
# ## ISC License
# 
# Copyright (c) 2013--2023, librosa development team.
# 
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
# 
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _hann(n: int) -> np.ndarray:
    return np.hanning(n + 1)[:-1]


def _stft(y: np.ndarray, nfft: int, hop: int, window: np.ndarray) -> np.ndarray:
    """Centered, zero padded STFT, matching the modern librosa defaults."""
    padded = np.pad(y, (nfft // 2, nfft // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, nfft)[::hop]
    result = np.empty((nfft // 2 + 1, len(frames)), np.complex64)
    # Bound FFT temporary memory independently of recording length.
    for start in range(0, len(frames), 256):
        result[:, start:start + 256] = np.fft.rfft(
            frames[start:start + 256] * window, axis=-1).T
    return result


def _spectral_blocks(y: np.ndarray, nfft: int, hop: int, window: np.ndarray,
                     block_frames: int = 256):
    """STFT blocks without constructing an audio-size padded copy."""
    count = 1 + len(y) // hop
    half = nfft // 2
    for frame in range(0, count, block_frames):
        last = min(count, frame + block_frames)
        left, right = frame * hop - half, (last - 1) * hop + half
        signal = y[max(0, left):min(len(y), right)]
        signal = np.pad(signal, (max(0, -left), max(0, right - len(y))))
        frames = np.lib.stride_tricks.sliding_window_view(signal, nfft)[::hop]
        yield frame, np.fft.rfft(frames * window, axis=-1).T.astype(np.complex64)


def estimate_tuning(y: np.ndarray) -> float:
    """NumPy reproduction of librosa's default piptrack tuning estimator."""
    all_pitches, all_magnitudes = [], []
    for _, spectrum in _spectral_blocks(y, 2048, 512, _hann(2048)):
        spectrum = np.abs(spectrum)
        avg = np.gradient(spectrum, axis=0)
        shift = np.zeros_like(spectrum)
        left, middle, right = spectrum[:-2], spectrum[1:-1], spectrum[2:]
        denominator = left - 2 * middle + right
        numerator = .5 * (left - right)
        np.divide(numerator, denominator, out=shift[1:-1], where=denominator != 0)
        shift[np.abs(shift) > 1] = 0
        # Strict on the left, inclusive on the right: librosa.localmax tie rule.
        gated = spectrum * (spectrum > .1 * np.max(spectrum, axis=0, keepdims=True))
        maxima = np.zeros_like(gated, dtype=bool)
        maxima[1:-1] = (gated[1:-1] > gated[:-2]) & (gated[1:-1] >= gated[2:])
        maxima[-1] = gated[-1] > gated[-2]
        frequencies = np.arange(spectrum.shape[0]) * 22050 / 2048
        maxima &= ((frequencies >= 150) & (frequencies < 4000))[:, None]
        bins, columns = np.nonzero(maxima)
        all_pitches.append((bins + shift[bins, columns]) * 22050 / 2048)
        all_magnitudes.append(spectrum[bins, columns] + .5 * avg[bins, columns] * shift[bins, columns])
    pitches = np.concatenate(all_pitches)
    magnitudes = np.concatenate(all_magnitudes)
    if not len(pitches):
        return 0.0
    pitches = pitches[magnitudes >= np.median(magnitudes)]
    residual = np.mod(36 * np.log2(pitches / 440), 1)
    residual[residual >= .5] -= 1
    counts, edges = np.histogram(residual, np.linspace(-.5, .5, 101))
    return float(edges[np.argmax(counts)])


def _alpha(frequencies: np.ndarray) -> np.ndarray:
    logf = np.log2(frequencies)
    bpo = np.empty_like(frequencies)
    bpo[0], bpo[-1] = 1 / (logf[1] - logf[0]), 1 / (logf[-1] - logf[-2])
    bpo[1:-1] = 2 / (logf[2:] - logf[:-2])
    ratio = 2 ** (2 / bpo)
    return (ratio - 1) / (ratio + 1)


def _basis(sr: float, frequencies: np.ndarray, alpha: np.ndarray,
           pseudo: bool = False) -> tuple[np.ndarray, int]:
    """Generate the modern wavelet FFT filters without scipy/librosa."""
    lengths = sr / (alpha * frequencies)
    original_size = int(2 ** np.ceil(np.log2(np.max(lengths))))
    nfft = max(original_size, 1024) if pseudo else original_size
    waves = []
    for length, frequency in zip(lengths, frequencies):
        indices = np.arange(-length // 2, length // 2, dtype=float)
        wave = np.exp(1j * indices * 2 * np.pi * frequency / sr) * _hann(len(indices))
        wave /= np.sum(np.abs(wave))
        pad = (original_size - len(wave)) // 2
        waves.append(np.pad(wave, (pad, original_size - len(wave) - pad)))
    waves = np.asarray(waves, np.complex64)
    waves *= lengths[:, None] / nfft
    filters = np.fft.fft(waves, n=nfft, axis=1)[:, :nfft // 2 + 1]
    magnitudes = np.abs(filters)
    sorted_magnitudes = np.sort(magnitudes, axis=1)
    totals = np.sum(magnitudes, axis=1, keepdims=True)
    cumulative = np.cumsum(sorted_magnitudes / totals, axis=1)
    thresholds = sorted_magnitudes[np.arange(len(filters)), np.argmin(cumulative < .01, axis=1)]
    filters[magnitudes < thresholds[:, None]] = 0
    return filters.astype(np.complex64), nfft


def _project(filters: np.ndarray, spectrum: np.ndarray) -> np.ndarray:
    # Sparse rows are typically only tens of frequency bins, so this avoids
    # a large dense GEMM and any SciPy dependency.
    output = np.empty((len(filters), spectrum.shape[1]), np.complex64)
    for row, coefficients in enumerate(filters):
        indices = np.flatnonzero(coefficients)
        for start in range(0, spectrum.shape[1], 512):
            output[row, start:start + 512] = np.sum(
                coefficients[indices, None] * spectrum[indices, start:start + 512],
                axis=0, dtype=np.complex64)
    return output


def _response(y: np.ndarray, filters: np.ndarray, nfft: int, hop: int,
              window: np.ndarray, magnitude_only: bool = False) -> np.ndarray:
    result = np.empty((len(filters), 1 + len(y) // hop), np.float32)
    for start, spectrum in _spectral_blocks(y, nfft, hop, window):
        if magnitude_only:
            spectrum = np.abs(spectrum)
        projected = np.abs(_project(filters, spectrum))
        result[:, start:start + projected.shape[1]] = projected
    return result


class PortableLVFrontend:
    """Return CQTV2's [frames, 288] magnitudes from mono float32/22050 PCM.

    Use result[:, 18:270] for the 252-bin network input. Default tuning=None
    estimates tuning just as the upstream extractor does. Generated FIR assets
    are checksum-validated by the app's model bundle before construction.
    """
    def __init__(self, asset_path: str | Path):
        with np.load(asset_path, allow_pickle=False) as archive:
            self.kernel = archive['downsample_hq'].astype(np.float64)
            self.metadata = json.loads(str(archive['metadata']))
        if self.metadata.get('format') != 'blaze-lv-hybrid-cqt-1':
            raise ValueError('Unsupported LV frontend assets')
        self.half = (len(self.kernel) - 1) // 2
        self._filter_cache = {}
        self.last_tuning = None

    def _down(self, y: np.ndarray) -> np.ndarray:
        result = np.empty((len(y) + 1) // 2, np.float32)
        # Overlap-save blocks keep FFT work memory bounded for long recordings.
        for start in range(0, len(y), 65536):
            end = min(len(y), start + 65536)
            left, right = start - self.half, end + self.half
            signal = y[max(0, left):min(len(y), right)]
            signal = np.pad(signal, (max(0, -left), max(0, right - len(y))))
            size = len(signal) + len(self.kernel) - 1
            nfft = 1 << (size - 1).bit_length()
            convolved = np.fft.irfft(np.fft.rfft(signal, n=nfft) *
                                     np.fft.rfft(self.kernel, n=nfft), n=nfft)
            samples = convolved[2 * self.half:2 * self.half + end - start:2]
            result[start // 2:(end + 1) // 2] = samples * np.sqrt(2)
        return result

    def _filters(self, tuning: float):
        if tuning in self._filter_cache:
            return self._filter_cache[tuning]
        fmin = 440 * 2 ** ((18 - 69) / 12) * 2 ** (tuning / 36)  # F#0
        frequencies = fmin * 2 ** (np.arange(288) / 36)
        alpha = _alpha(frequencies)
        lengths = 22050 / (alpha * frequencies)
        nfull = int(np.sum(2 ** np.ceil(np.log2(lengths)) >= 1024))
        pseudo, pseudo_fft = _basis(22050, frequencies[nfull:], alpha[nfull:], True)
        full_frequencies, full_alpha = frequencies[:nfull], alpha[:nfull]
        cutoff = np.max(full_frequencies * (1 + .5 * 1.50018310546875 * full_alpha))
        octaves = int(np.ceil(nfull / 36))
        early = min(max(0, int(np.ceil(np.log2(11025 / cutoff)) - 1) - 1),
                    max(0, 9 - octaves + 1))
        sr = 22050 / 2 ** early
        full = []
        for octave in range(octaves):
            sl = slice(-36, None) if octave == 0 else slice(-36 * (octave + 1), -36 * octave)
            filt, nfft = _basis(sr / 2 ** octave, full_frequencies[sl], full_alpha[sl])
            filt *= np.sqrt(2 ** octave)
            full.append((filt, nfft))
        scale = np.sqrt(sr / (full_alpha * full_frequencies)).astype(np.float32)
        result = (np.abs(pseudo).astype(np.complex64), pseudo_fft, full, scale, early)
        # One recording usually needs one tuning value. Limit retained bases.
        self._filter_cache.clear()
        self._filter_cache[tuning] = result
        return result

    def extract(self, pcm: np.ndarray, tuning: float | None = None) -> np.ndarray:
        y = np.asarray(pcm, np.float32)
        if y.ndim != 1 or not len(y) or not all(np.all(np.isfinite(y[start:start + 65536]))
                                              for start in range(0, len(y), 65536)):
            raise ValueError('Expected nonempty finite mono PCM')
        if tuning is None:
            tuning = estimate_tuning(y)
        self.last_tuning = float(tuning)
        pseudo_basis, pseudo_fft, full_filters, scale, early = self._filters(float(tuning))
        pseudo = _response(y, pseudo_basis, pseudo_fft, 512, _hann(pseudo_fft), True)
        pseudo /= np.sqrt(pseudo_fft)
        hop = 512
        for _ in range(early):
            y, hop = self._down(y), hop // 2
        responses = []
        for basis, nfft in full_filters:
            responses.append(_response(y, basis, nfft, hop, np.ones(nfft)))
            y, hop = self._down(y), hop // 2
        frame_count = min(pseudo.shape[-1], *(response.shape[-1] for response in responses))
        full = np.concatenate([response[:, :frame_count] for response in responses[::-1]], axis=0)
        full /= scale[:, None]
        return np.concatenate((full, pseudo[:, :frame_count]), axis=0).T.astype(np.float32)

