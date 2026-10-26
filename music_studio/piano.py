"""Five-stem separation and piano isolation with Deezer's Spleeter U-Nets.

One model is evaluated as five spectral graphs, sequentially to bound memory.
The accompaniment is the input minus estimated piano, preserving the full mix.
"""
from pathlib import Path
import hashlib
import shutil
import tempfile
import threading
import numpy as np
import onnxruntime as ort
from .piano_assets import MODELS
from .stems import Separator, check_cancel, _write_header, MAX_BYTES, DISK_RESERVE

FFT, HOP, FRAMES, BINS = 4096, 1024, 512, 1024
SEGMENT = (FRAMES - 3) * HOP
WINDOW = (.5 - .5 * np.cos(2 * np.pi * np.arange(FFT) / FFT)).astype(np.float32)


def analyse(audio):
    padded = np.pad(audio, ((0, 0), (3072, 4096)))
    windows = np.lib.stride_tricks.sliding_window_view(padded, FFT, axis=-1)[:, ::HOP][:, :FRAMES]
    spec = np.fft.rfft(windows * WINDOW, axis=-1).astype(np.complex64)
    magnitude = np.zeros((1, 2, FRAMES, BINS), dtype=np.float32)
    magnitude[0, :, :spec.shape[1]] = np.abs(spec[:, :, :BINS])
    return spec, magnitude


def ratio_masks(logits, magnitude):
    # Reproduce Spleeter's joint softmax, then its power-2 ratio mask.
    values = np.asarray(logits, dtype=np.float32)
    values -= values.max(axis=0, keepdims=True)
    np.exp(values, out=values)
    values /= values.sum(axis=0, keepdims=True)
    values *= magnitude[0][None]
    np.square(values, out=values)
    return (values + 1e-10 / 5) / (values.sum(axis=0, keepdims=True) + 1e-10)


def piano_mask(logits, magnitude):
    return ratio_masks(logits, magnitude)[2]


def synthesise(spec, mask, length):
    filtered = np.zeros_like(spec)
    filtered[:, :, :BINS] = spec[:, :, :BINS] * mask[:, :spec.shape[1]]
    frames = np.fft.irfft(filtered, n=FFT, axis=-1).astype(np.float32)
    size = (frames.shape[1] - 1) * HOP + FFT
    out = np.zeros((2, size), dtype=np.float32)
    weights = np.zeros(size, dtype=np.float32)
    for index in range(frames.shape[1]):
        start = index * HOP
        out[:, start:start + FFT] += frames[:, index] * WINDOW
        weights[start:start + FFT] += WINDOW * WINDOW
    np.divide(out, weights[None], out=out, where=weights[None] > 1e-8)
    return out[:, 3072:3072 + length]


class PianoSeparator(Separator):
    outputs = ('piano', 'accompaniment')
    message = 'Isolating the piano…'
    completed = 'Your piano track is ready.'

    def _estimates(self, audio, spec, logits, features):
        piano = synthesise(spec, piano_mask(logits, features), SEGMENT)
        return np.stack((piano, audio - piano))

    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        super().__init__(model_directory, ffmpeg)
        self.directory = self.directory / 'piano'

    def _graph(self, name, features, event):
        check_cancel(event)
        meta = MODELS[name]
        path = self.directory / meta['file']
        if not path.is_file() or path.stat().st_size != meta['bytes']:
            raise ValueError('The instrument model is missing. Reinstall the complete Mac app.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError('The instrument model checksum is invalid. Reinstall the Mac app.')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        ort.disable_telemetry_events()
        self.session = ort.InferenceSession(data, sess_options=options, providers=['CPUExecutionProvider'])
        try:
            check_cancel(event)
            if self.session.get_inputs()[0].shape != [1, 2, FRAMES, BINS]:
                raise ValueError('The instrument model has an incompatible interface.')
            # Reuse the existing interruptible ORT runner with this graph's names.
            run_options, finished = ort.RunOptions(), threading.Event()
            def interrupt():
                while not finished.wait(.02):
                    if event.is_set():
                        run_options.terminate = True
                        return
            watcher = threading.Thread(target=interrupt, daemon=True)
            watcher.start()
            try:
                result = self.session.run(['y'], {'x': features}, run_options)[0]
            except Exception:
                check_cancel(event)
                raise
            finally:
                finished.set()
                watcher.join(timeout=1)
            check_cancel(event)
            if result.shape != features.shape or not np.isfinite(result).all():
                raise ValueError('The instrument model returned invalid estimates.')
            return result[0]
        finally:
            self.session = None

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
        paths = {name: output / (name + '.wav') for name in self.outputs}
        streams = []
        try:
            with tempfile.TemporaryDirectory(prefix='blaze-piano-') as temporary:
                decoded = Path(temporary) / 'audio.f32'
                progress(0, 'Reading the recording…')
                count = self._decode(source, decoded, event)
                if shutil.disk_usage(output).free < count * 8 * len(self.outputs) + DISK_RESERVE:
                    raise ValueError('There is not enough free space to save the separated tracks.')
                pcm = np.memmap(decoded, mode='r', dtype='<f4', shape=(count, 2))
                try:
                    for path in paths.values():
                        stream = path.open('wb'); streams.append(stream); _write_header(stream, count)
                    stride = SEGMENT // 2
                    weight = np.minimum(np.arange(1, SEGMENT + 1), np.arange(SEGMENT, 0, -1)).astype(np.float32)
                    weight /= weight.max()
                    accumulated = np.zeros((len(self.outputs), 2, SEGMENT), dtype=np.float32)
                    denominator = np.zeros(SEGMENT, dtype=np.float32)
                    for offset in range(0, count, stride):
                        check_cancel(event)
                        length = min(SEGMENT, count - offset)
                        audio = np.zeros((2, SEGMENT), dtype=np.float32)
                        audio[:, :length] = pcm[offset:offset + length].T
                        if not np.isfinite(audio).all():
                            raise ValueError('The recording contains invalid audio samples.')
                        spec, features = analyse(audio)
                        logits = []
                        for index, name in enumerate(('drums', 'bass', 'piano', 'other', 'vocals')):
                            logits.append(self._graph(name, features, event))
                            progress(.03 + .94 * min(1, (offset + stride * (index + 1) / 5) / count),
                                     self.message)
                        estimates = self._estimates(audio, spec, logits, features)
                        if not np.isfinite(estimates).all():
                            raise ValueError('The model returned invalid audio samples.')
                        accumulated[:, :, :length] += estimates[:, :, :length] * weight[:length]
                        denominator[:length] += weight[:length]
                        written = min(stride, count - offset)
                        block = accumulated[:, :, :written] / denominator[None, None, :written]
                        for stream, samples in zip(streams, block):
                            stream.write(np.asarray(samples.T, dtype='<f4').tobytes())
                        accumulated[:, :, :-stride] = accumulated[:, :, stride:]
                        accumulated[:, :, -stride:] = 0
                        denominator[:-stride] = denominator[stride:]
                        denominator[-stride:] = 0
                finally:
                    del pcm
            check_cancel(event)
            for stream in streams: stream.close()
            streams.clear()
            progress(1, self.completed)
            return paths
        except Exception:
            for stream in streams: stream.close()
            for path in paths.values(): path.unlink(missing_ok=True)
            raise


class FiveStemSeparator(PianoSeparator):
    outputs = ('vocals', 'drums', 'bass', 'piano', 'other')
    message = 'Separating vocals, drums, bass, piano and other…'
    completed = 'Your five stems are ready.'

    def _estimates(self, audio, spec, logits, features):
        masks = ratio_masks(logits, features)
        # Graph order: drums, bass, piano, other, vocals. Present vocals first.
        estimates = np.stack([synthesise(spec, masks[i], SEGMENT) for i in (4, 0, 1, 2, 3)])
        # Preserve the original's unmodeled high band and numerical residual in
        # Other so five unity-gain exports reconstruct the input recording.
        estimates[4] += audio - estimates.sum(axis=0)
        return estimates
