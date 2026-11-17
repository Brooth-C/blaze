"""Full-band acoustic-piano estimate from the original Mega53 complex head.

One shared trunk and one independent piano estimator, not a family-energy
projection and not synthesized replacement audio. Accompaniment is the residual.
"""
import json
import numpy as np

from .instruments import InstrumentSeparator, FFT, HOP, SEGMENT
from .instrument_assets import MODELS
from .native_piano_assets import HEAD, manifest
from .roformer_transform import stft_bands_last, istft_bands_last
from .stems import check_cancel


def apply_complex_mask(spectrum, mask):
    """Preserve complex-mask arithmetic with one reusable product workspace."""
    a, b = spectrum[..., 0], spectrum[..., 1]
    c, d = mask[..., 0], mask[..., 1]
    dtype = np.result_type(spectrum.dtype, mask.dtype)
    result = np.empty(spectrum.shape, dtype=dtype)
    scratch = np.empty(spectrum.shape[:-1], dtype=dtype)
    np.multiply(a, c, out=result[..., 0])
    np.multiply(b, d, out=scratch)
    np.subtract(result[..., 0], scratch, out=result[..., 0])
    np.multiply(a, d, out=result[..., 1])
    np.multiply(b, c, out=scratch)
    np.add(result[..., 1], scratch, out=result[..., 1])
    return result


def piano_and_backing(audio, piano):
    """Preserve residual precision while packing directly into final FP32 stems."""
    estimates = np.empty((2, *piano.shape), dtype=np.float32)
    estimates[0] = piano
    np.subtract(audio, piano, out=estimates[1], dtype=np.result_type(audio.dtype, piano.dtype))
    return estimates


class NativePianoSeparator(InstrumentSeparator):
    outputs = ('piano', 'accompaniment')
    other_index = 1
    processing_message = 'Separating the piano and preserving its detail…'
    completed_message = 'Your piano and accompaniment are ready.'

    def __init__(self, model_directory=None, ffmpeg='ffmpeg', runtime_backend=None):
        super().__init__(model_directory, ffmpeg, runtime_backend=runtime_backend)
        self.piano_directory = self.directory.parent / 'native-piano'

    def _load(self, event):
        super()._load(event)
        check_cancel(event)
        try:
            if json.loads((self.piano_directory / 'manifest.json').read_text()) != manifest():
                raise ValueError('Incompatible piano manifest')
            if (self.piano_directory / HEAD['file']).stat().st_size != HEAD['bytes']:
                raise ValueError('Invalid piano model size')
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('The native piano model is missing or damaged. Reinstall the complete Mac app.') from error

    def _mask(self, features, event):
        latent = features
        for index, name in enumerate(['front', *[f'block{i}' for i in range(12)]]):
            latent = self._graph(MODELS[name], latent, event)
            self.block_progress((index + 1) / 14)
        shared_directory = self.directory
        try:
            self.directory = self.piano_directory
            mask = self._graph(HEAD, latent, event)
        finally:
            self.directory = shared_directory
        self.block_progress(1)
        return mask

    def _chunk(self, audio, event):
        features = stft_bands_last(audio, FFT, HOP)
        mask = self._mask(features, event)
        check_cancel(event)
        if mask.shape != (1, 1, 2050, 1723, 2) or not np.isfinite(mask).all():
            raise ValueError('The piano model returned an invalid complex mask.')
        masked = apply_complex_mask(features[0], mask[0, 0])
        # Reconstruction only needs the owned masked spectrum. Release both
        # input spectra before allocating inverse-FFT/work/output buffers;
        # the borrowed MLX mask otherwise keeps its GPU allocation alive too.
        del features, mask
        masked[:2] = 0
        piano = istft_bands_last(masked, 2, FFT, HOP, SEGMENT)
        return piano_and_backing(audio, piano)
