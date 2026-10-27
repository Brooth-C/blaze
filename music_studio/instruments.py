"""Refine Other into guitar, strings, brass, synths and a full-band residual.

Mega 53's selected independent heads supply spectral evidence. Related guitar
heads are max-pooled rather than summed. Nonnegative, bounded family masks
partition the input spectrum and retain unexplained audio in Other.
"""
from pathlib import Path
import json
import tempfile
import threading

import numpy as np

from .roformer import RoformerSeparator, QualityFiveStemSeparator
from .roformer_transform import stft_bands_last, istft_bands_last
from .stems import check_cancel
from .instrument_assets import CHECKPOINT_SHA, MODELS, SELECTED

SEGMENT, FFT, HOP = 882000, 2048, 512
FAMILIES = ('guitar', 'strings', 'brass', 'synths', 'other')
NINE_STEMS = ('vocals', 'drums', 'bass', 'piano', *FAMILIES)


def family_masks(scores):
    values = np.asarray(scores, dtype=np.float32)
    if values.shape[0] != 4 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('The instrument model returned invalid family scores.')
    denominator = np.maximum(1, values.sum(axis=0, dtype=np.float64))
    masks = np.asarray(values / denominator[None], dtype=np.float32)
    residual = np.maximum(0, 1 - masks.sum(axis=0))
    return np.concatenate((masks, residual[None]), axis=0)


class InstrumentSeparator(RoformerSeparator):
    outputs = FAMILIES
    segment_samples = SEGMENT
    other_index = 4
    processing_message = 'Separating guitar, strings, brass and synths…'
    completed_message = 'The instrument tracks are ready.'

    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        super().__init__(model_directory, ffmpeg)
        self.directory = self.directory.parent / 'instruments'

    def _load(self, event):
        check_cancel(event)
        try:
            metadata = json.loads((self.directory / 'manifest.json').read_text())
            if (len(MODELS) != 19 or not isinstance(metadata, dict) or metadata.get('models') != MODELS
                    or metadata.get('license') != 'MIT' or metadata.get('checkpoint_sha256') != CHECKPOINT_SHA):
                raise ValueError('Invalid instrument manifest')
            for meta in MODELS.values():
                path = self.directory / meta['file']
                if not path.is_file() or path.stat().st_size != meta['bytes']:
                    raise ValueError('Invalid instrument asset size')
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('The instrument model is missing or damaged. Reinstall the complete Mac app.') from error

    def _scores(self, features, event):
        latent = features
        trunk_names = ['front', *[f'block{i}' for i in range(12)]]
        for index, name in enumerate(trunk_names):
            latent = self._graph(MODELS[name], latent, event)
            self.block_progress((index + 1) / 19)
        scores = np.zeros((4, 2050, 1723), dtype=np.float32)
        groups = (0, 0, 0, 1, 2, 3)
        for index, (name, group) in enumerate(zip(SELECTED, groups)):
            mask = self._graph(MODELS['head-' + name], latent, event)[0, 0]
            with np.errstate(over='ignore', invalid='ignore'):
                energy = np.square(mask).sum(axis=-1)
            np.maximum(scores[group], energy, out=scores[group])
            self.block_progress((14 + index) / 19)
        # Keep the unmodeled DC component in Other, as in original inference.
        scores[:, :2] = 0
        return scores

    def _chunk(self, audio, event):
        features = stft_bands_last(audio, FFT, HOP)
        masks = family_masks(self._scores(features, event))
        return np.stack([istft_bands_last(features[0] * mask[..., None], 2, FFT, HOP, SEGMENT)
                         for mask in masks]).astype(np.float32)


class NineStemSeparator:
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        self.models, self.ffmpeg = model_directory, ffmpeg

    def separate(self, source, output_dir, progress=None, cancel_event=None):
        event = cancel_event or threading.Event()
        progress = progress or (lambda fraction, message: None)
        check_cancel(event)
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Stem separation requires a new empty output folder.')
        paths = {}
        try:
            with tempfile.TemporaryDirectory(prefix='.instruments-', dir=output) as temporary:
                temporary = Path(temporary)
                main = QualityFiveStemSeparator(self.models, self.ffmpeg).separate(
                    source, temporary / 'main', lambda f, m: progress(f * .5, m), event)
                instruments = InstrumentSeparator(self.models, self.ffmpeg).separate(
                    main['other'], temporary / 'instruments', lambda f, m: progress(.5 + f * .49, m), event)
                check_cancel(event)
                sources = {name: main[name] for name in ('vocals', 'drums', 'bass', 'piano')}
                sources.update(instruments)
                if set(sources) != set(NINE_STEMS):
                    raise ValueError('The instrument model did not produce all nine tracks.')
                for name in NINE_STEMS:
                    check_cancel(event)
                    destination = output / (name + '.wav')
                    sources[name].rename(destination)
                    paths[name] = destination
            check_cancel(event)
            progress(1, 'Your nine stems are ready.')
            return paths
        except Exception:
            for path in paths.values():
                path.unlink(missing_ok=True)
            raise
