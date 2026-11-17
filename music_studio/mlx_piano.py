"""Fused-Metal backend used by default for piano isolation on Apple Silicon."""
import hashlib
import json
import time

from .native_piano import NativePianoSeparator
from .mlx_piano_assets import WEIGHTS, manifest
from .stems import check_cancel


class MlxPianoSeparator(NativePianoSeparator):
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        # MLX owns every neural layer here; do not initialize a redundant
        # Core ML runtime inherited from the ONNX implementation.
        super().__init__(model_directory, ffmpeg, runtime_backend='cpu')
        self.mlx_directory = self.directory.parent/'mlx-piano'
        self.model = None
        self.mlx_records = []
        self.load_seconds = 0.

    def _load(self, event):
        started = time.monotonic()
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
        self.load_seconds = time.monotonic()-started
        check_cancel(event)

    def _mask(self, features, event):
        start = time.monotonic()
        result = self.model.predict(features, check=lambda: check_cancel(event), progress=self.block_progress)
        self.mlx_records.append({'seconds': time.monotonic()-start,
                                 'process_lifetime_peak_allocated_bytes': self.model.mx.get_peak_memory(),
                                 'sequence_batch_tokens': self.model.batch_tokens,
                                 'metal_fused_attention_required': True,
                                 'weights_sha256': WEIGHTS['sha256']})
        return result

    def separate(self, *args, **kwargs):
        started = time.monotonic()
        first_record = len(self.mlx_records)
        self.load_seconds = 0.
        completed = False
        try:
            result = super().separate(*args, **kwargs)
            completed = True
            return result
        finally:
            if self.model is not None:
                self.model.close()
                self.model = None
            records = self.mlx_records[first_record:]
            print('BLAZE_SEPARATION_TIMING ' + json.dumps({
                'backend': 'mlx-metal', 'completed': completed,
                'total_seconds': round(time.monotonic()-started, 3),
                'model_load_seconds': round(self.load_seconds, 3),
                'inference_seconds': round(sum(row['seconds'] for row in records), 3),
                'completed_chunks': len(records),
                'sequence_batch_tokens': max((row['sequence_batch_tokens'] for row in records), default=0),
                'process_lifetime_peak_allocated_bytes': max((row['process_lifetime_peak_allocated_bytes'] for row in records), default=0),
            }), flush=True)
