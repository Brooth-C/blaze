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


class NativePianoSeparator(InstrumentSeparator):
    outputs = ('piano', 'accompaniment')
    other_index = 1
    processing_message = 'Separating the piano and preserving its detail…'
    completed_message = 'Your piano and accompaniment are ready.'

    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        super().__init__(model_directory, ffmpeg)
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
        a, b = features[0, ..., 0], features[0, ..., 1]
        c, d = mask[0, 0, ..., 0], mask[0, 0, ..., 1]
        masked = np.stack((a * c - b * d, a * d + b * c), axis=-1)
        masked[:2] = 0
        piano = istft_bands_last(masked, 2, FFT, HOP, SEGMENT)
        return np.stack((piano, audio - piano)).astype(np.float32)
