"""Local FP32 BS-RoFormer separation followed by a separate piano stage.

The spectral transform is adapted from Santiago Quiroz Upegui's MIT port;
see tools/roformer/LICENSE-Port.txt. No Torch or online inference at runtime.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tempfile
import threading

import numpy as np
import onnxruntime as ort

from .stems import Separator, check_cancel, _write_header, MAX_BYTES, DISK_RESERVE
from .roformer_transform import stft_bands_last, istft_bands_last

RATE, SEGMENT, FFT, HOP = 44100, 485100, 2048, 441
STEMS = ('drums', 'bass', 'other', 'vocals')
CHECKPOINT_SHA = '3e9daecd70aaed5b5a0d1f861cc4d77eaa45afb3fc6301b1cf32c1be0f5868fb'


class RoformerSeparator(Separator):
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        super().__init__(model_directory, ffmpeg)
        self.directory = self.directory / 'roformer'
        self.block_progress = lambda fraction: None

    def _load(self, event):
        from .roformer_assets import MODELS
        check_cancel(event)
        try:
            metadata = json.loads((self.directory / 'manifest.json').read_text())
            if (metadata.get('models') != MODELS or metadata.get('license') != 'MIT'
                    or metadata.get('checkpoint_sha256') != CHECKPOINT_SHA):
                raise ValueError('Incompatible manifest')
            for meta in MODELS.values():
                path = self.directory / meta['file']
                if not path.is_file() or path.stat().st_size != meta['bytes']:
                    raise ValueError('Invalid model size')
        except (OSError, ValueError, TypeError) as error:
            raise ValueError('The stem model is missing or damaged. Reinstall the complete Mac app.') from error

    def _graph(self, meta, features, event):
        check_cancel(event)
        path = self.directory / meta['file']
        data = path.read_bytes()
        if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError('The stem model checksum is invalid. Reinstall the complete Mac app.')
        check_cancel(event)
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 2)
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        options.add_session_config_entry('session.disable_prepacking', '1')
        ort.disable_telemetry_events()
        self.session = ort.InferenceSession(data, sess_options=options, providers=['CPUExecutionProvider'])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].name != 'x' or inputs[0].shape != meta['input_shape']
                or inputs[0].type != 'tensor(float)' or len(outputs) != 1
                or outputs[0].name != 'y' or outputs[0].shape != meta['output_shape']
                or outputs[0].type != 'tensor(float)'):
            self.session = None
            raise ValueError('The stem model interface is incompatible.')
        check_cancel(event)

        options, finished = ort.RunOptions(), threading.Event()
        def interrupt():
            while not finished.wait(.02):
                if event.is_set():
                    options.terminate = True
                    return
        watcher = threading.Thread(target=interrupt, daemon=True)
        watcher.start()
        try:
            check_cancel(event)
            result = self.session.run(['y'], {'x': features}, options)[0]
            check_cancel(event)
            if list(result.shape) != meta['output_shape'] or not np.isfinite(result).all():
                raise ValueError('The stem model returned invalid estimates.')
            return result
        except Exception:
            check_cancel(event)
            raise
        finally:
            finished.set()
            watcher.join(timeout=1)
            self.session = None

    def _predict(self, features, event):
        from .roformer_assets import MODELS
        # Ten graphs are one checkpoint, not an ensemble. Loading one block at
        # a time releases ORT subgraph arenas between transformer layers.
        for index, meta in enumerate(MODELS.values()):
            features = self._graph(meta, features, event)
            self.block_progress((index + 1) / len(MODELS))
        return features

    def _chunk(self, audio, event):
        features = stft_bands_last(audio, FFT, HOP)
        mask = self._predict(features, event)
        check_cancel(event)
        if mask.shape != (1, 4, 2050, 1101, 2) or not np.isfinite(mask).all():
            raise ValueError('The stem model returned invalid estimates.')
        a, b = features[0, ..., 0], features[0, ..., 1]
        c, d = mask[0, ..., 0], mask[0, ..., 1]
        masked = np.stack((a * c - b * d, a * d + b * c), axis=-1)
        masked[:, :2] = 0  # Original inference removes the stereo DC bins.
        return np.stack([istft_bands_last(value, 2, FFT, HOP, SEGMENT) for value in masked]).astype(np.float32)

    def separate(self, source, output_dir, progress=None, cancel_event=None):
        event = cancel_event or threading.Event()
        progress = progress or (lambda fraction, message: None)
        check_cancel(event)
        source = Path(source).resolve(strict=True)
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
            raise ValueError('Choose an audio or video file smaller than 2 GB.')
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Stem separation requires a new empty output folder.')
        paths = {name: output / (name + '.wav') for name in STEMS}
        streams = []
        try:
            progress(0, 'Opening the high-quality stem model…')
            self._load(event)
            with tempfile.TemporaryDirectory(prefix='blaze-roformer-') as temporary:
                decoded = Path(temporary) / 'audio.f32'
                count = self._decode(source, decoded, event)
                if shutil.disk_usage(output).free < count * 8 * 4 + DISK_RESERVE:
                    raise ValueError('There is not enough free space to save the separated tracks.')
                pcm = np.memmap(decoded, mode='r', dtype='<f4', shape=(count, 2))
                try:
                    for path in paths.values():
                        stream = path.open('wb'); streams.append(stream); _write_header(stream, count)
                    stride = SEGMENT // 2
                    border = stride if count > 2 * stride else 0
                    total = count + 2 * border
                    fade = SEGMENT // 10
                    weight = np.ones(SEGMENT, dtype=np.float32)
                    weight[:fade] = np.linspace(0, 1, fade)
                    weight[-fade:] = np.linspace(1, 0, fade)
                    accumulated = np.zeros((4, 2, SEGMENT), dtype=np.float32)
                    denominator = np.zeros(SEGMENT, dtype=np.float32)
                    written_frames = 0
                    for offset in range(0, total, stride):
                        check_cancel(event)
                        length = min(SEGMENT, total - offset)
                        indices = np.arange(offset, offset + length) - border
                        indices = np.where(indices < 0, -indices, indices)
                        indices = np.where(indices >= count, 2 * count - 2 - indices, indices)
                        audio = np.asarray(pcm[indices].T, dtype=np.float32)
                        if not np.isfinite(audio).all():
                            raise ValueError('The recording contains invalid audio samples.')
                        if length < SEGMENT:
                            audio = np.pad(audio, ((0, 0), (0, SEGMENT - length)),
                                           mode='reflect' if length > stride else 'constant')
                        self.block_progress = lambda fraction: progress(
                            .03 + .95 * min(1, (offset + min(stride, total - offset) * fraction) / total),
                            'Separating vocals, drums, bass and other…')
                        estimates = self._chunk(audio, event)
                        if estimates.shape != (4, 2, SEGMENT) or not np.isfinite(estimates).all():
                            raise ValueError('The model returned invalid audio samples.')
                        current_weight = weight.copy()
                        if offset == 0:
                            current_weight[:fade] = 1
                        elif offset + stride >= total:
                            current_weight[-fade:] = 1
                        accumulated[:, :, :length] += estimates[:, :, :length] * current_weight[:length]
                        denominator[:length] += current_weight[:length]
                        written = min(stride, total - offset)
                        block = accumulated[:, :, :written] / denominator[None, None, :written]
                        left, right = max(0, border - offset), min(written, border + count - offset)
                        if right > left:
                            block = block[:, :, left:right]
                            original = np.asarray(pcm[offset + left - border:offset + right - border].T)
                            # Keep original gain/bandwidth and unity-gain reconstruction.
                            block[2] += original - block.sum(axis=0)
                            for stream, samples in zip(streams, block):
                                stream.write(np.asarray(samples.T, dtype='<f4').tobytes())
                            written_frames += right - left
                        accumulated[:, :, :-stride] = accumulated[:, :, stride:]
                        accumulated[:, :, -stride:] = 0
                        denominator[:-stride] = denominator[stride:]
                        denominator[-stride:] = 0
                        progress(.03 + .95 * min(1, (offset + written) / total),
                                 'Separating vocals, drums, bass and other…')
                    if written_frames != count:
                        raise ValueError('The separated recording has an incomplete duration.')
                finally:
                    del pcm
            check_cancel(event)
            for stream in streams: stream.close()
            streams.clear()
            progress(1, 'The main stems are ready.')
            return paths
        except Exception:
            for stream in streams: stream.close()
            for path in paths.values(): path.unlink(missing_ok=True)
            raise
        finally:
            self.session = None


class QualityFiveStemSeparator:
    """BS-RoFormer main stems, then extract piano from its remaining music."""
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        self.models, self.ffmpeg = model_directory, ffmpeg

    def separate(self, source, output_dir, progress=None, cancel_event=None):
        from .piano import PianoSeparator
        event = cancel_event or threading.Event()
        progress = progress or (lambda fraction, message: None)
        check_cancel(event)
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if any(output.iterdir()):
            raise ValueError('Stem separation requires a new empty output folder.')
        paths = {}
        try:
            with tempfile.TemporaryDirectory(prefix='.quality-', dir=output) as temporary:
                temporary = Path(temporary)
                main = RoformerSeparator(self.models, self.ffmpeg).separate(
                    source, temporary / 'main', lambda f, m: progress(f * .75, m), event)
                piano = PianoSeparator(self.models, self.ffmpeg).separate(
                    main['other'], temporary / 'piano', lambda f, m: progress(.75 + f * .24, m), event)
                check_cancel(event)
                sources = {'vocals': main['vocals'], 'drums': main['drums'], 'bass': main['bass'],
                           'piano': piano['piano'], 'other': piano['accompaniment']}
                for name, path in sources.items():
                    check_cancel(event)
                    destination = output / (name + '.wav')
                    path.rename(destination)
                    paths[name] = destination
            check_cancel(event)
            progress(1, 'Your five stems are ready.')
            return paths
        except Exception:
            for path in paths.values(): path.unlink(missing_ok=True)
            raise
