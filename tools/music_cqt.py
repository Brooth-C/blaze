"""Research-only portable reproduction of BTC's librosa 0.6.3 CQT."""
from pathlib import Path
import sys
import types
import numpy as np
import numba
import torch
import torch.nn.functional as F
import resampy

np.float = float
np.complex = complex
np.int = int
np.bool = bool
module = types.ModuleType('numba.decorators')
module.jit = numba.jit
sys.modules['numba.decorators'] = module
import os
sys.path.insert(0, os.environ['BLAZE_LEGACY_LIBROSA'])
import librosa
from librosa.core import constantq


class CQT(torch.nn.Module):
    def __init__(self):
        super().__init__()
        table, precision, _ = resampy.filters.get_filter('kaiser_fast')
        step = precision // 2
        half = len(table) // step - 1
        coefficients = table[np.abs(np.arange(-half, half + 1)) * step] * .5
        self.half = half
        self.register_buffer('kernel', torch.from_numpy(coefficients.astype(np.float32)).reshape(1, 1, -1))
        fmin = librosa.note_to_hz('C1')
        frequencies = librosa.cqt_frequencies(144, fmin, bins_per_octave=24)[-24:]
        q = 1 / (2 ** (1 / 24) - 1)
        cutoff = max(frequencies) * (1 + .5 * librosa.filters.window_bandwidth('hann') / q)
        self.early = getattr(constantq, "__early_downsample_count")(11025, cutoff, 2048, 6)
        sample_rate = 22050 / 2 ** self.early
        basis, self.nfft, _ = getattr(constantq, "__cqt_filter_fft")(sample_rate, min(frequencies), 24, 24, 0, 1, 1, .01, window='hann')
        basis = basis.toarray()
        self.register_buffer('basis_real', torch.from_numpy(basis.real))
        self.register_buffer('basis_imag', torch.from_numpy(basis.imag))
        lengths = librosa.filters.constant_q_lengths(sample_rate, fmin, n_bins=144, bins_per_octave=24)
        self.register_buffer('lengths', torch.from_numpy(np.sqrt(lengths)).reshape(1, 144, 1))
        self.register_buffer('window', torch.ones(self.nfft, dtype=torch.float64))

    def down(self, signal):
        old_length = signal.shape[-1]
        result = F.conv1d(F.pad(signal.unsqueeze(1), (self.half, self.half)), self.kernel, stride=2).squeeze(1)
        # resampy floors output length, then librosa fixes odd lengths by adding zero.
        result = result[:, :old_length // 2]
        result = F.pad(result, (0, old_length % 2))
        return (result.double() / np.sqrt(.5)).float()

    def reflect(self, signal):
        length = signal.shape[-1]
        indices = torch.arange(-self.nfft // 2, length + self.nfft // 2, device=signal.device)
        indices = indices.remainder(2 * (length - 1))
        indices = torch.where(indices < length, indices, 2 * (length - 1) - indices)
        return signal.index_select(-1, indices)

    def forward(self, signal):
        for _ in range(self.early):
            signal = self.down(signal)
        hop = 2048 // 2 ** self.early
        responses = []
        for octave in range(6):
            if octave:
                signal = self.down(signal)
                hop //= 2
            spectrum = torch.stft(self.reflect(signal).double(), self.nfft, hop_length=hop,
                                  window=self.window, center=False, return_complex=False)
            real = torch.matmul(self.basis_real, spectrum[..., 0]) - torch.matmul(self.basis_imag, spectrum[..., 1])
            imag = torch.matmul(self.basis_real, spectrum[..., 1]) + torch.matmul(self.basis_imag, spectrum[..., 0])
            responses.append(torch.sqrt(real.square() + imag.square()) * np.sqrt(2) ** octave)
        frames = torch._shape_as_tensor(responses[0])[-1]
        for value in responses[1:]:
            frames = torch.minimum(frames, torch._shape_as_tensor(value)[-1])
        values = torch.cat([value[:, :, :frames] for value in responses[::-1]], dim=1) / self.lengths
        return torch.log(values + 1e-6).transpose(1, 2)


