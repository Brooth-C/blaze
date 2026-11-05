"""Fused-Metal backend used by default for piano isolation on Apple Silicon."""
import hashlib
import json
import time

from .native_piano import NativePianoSeparator
from .mlx_piano_assets import WEIGHTS, manifest
from .stems import check_cancel


class MlxPianoSeparator(NativePianoSeparator):
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        super().__init__(model_directory, ffmpeg)
        self.mlx_directory = self.directory.parent/'mlx-piano'
        self.model = None
        self.mlx_records = []

    def _load(self, event):
        check_cancel(event)
        try:
            path = self.mlx_directory/WEIGHTS['file']
            if json.loads((self.mlx_directory/'manifest.json').read_text()) != manifest() or path.stat().st_size != WEIGHTS['bytes']:
                raise ValueError('Incompatible MLX piano assets')
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest() != WEIGHTS['sha256']:
                    raise ValueError('Invalid MLX piano checksum')
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('The MLX piano model is missing or damaged. Reinstall the complete Mac app.') from error
        check_cancel(event)
        from .mlx_piano_model import PianoModel
        self.model = PianoModel(path)
        check_cancel(event)

    def _mask(self, features, event):
        start = time.monotonic()
        result = self.model.predict(features, check=lambda: check_cancel(event), progress=self.block_progress)
        self.mlx_records.append({'seconds': time.monotonic()-start,
                                 'process_lifetime_peak_allocated_bytes': self.model.mx.get_peak_memory(),
                                 'metal_fused_attention_required': True,
                                 'weights_sha256': WEIGHTS['sha256']})
        return result

    def separate(self, *args, **kwargs):
        try:
            return super().separate(*args, **kwargs)
        finally:
            if self.model is not None:
                self.model.close()
                self.model = None
