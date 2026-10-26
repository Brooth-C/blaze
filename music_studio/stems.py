"""Offline, bounded-memory SCNet separation using the bundled ONNX model.

The spectral transforms follow official SCNet and the pinned spectral exporter.
Fixed 7.8-second contexts use deterministic 50% triangular overlap-add; no
test-time shifts, extra models, per-stem gain normalization or remote inference.
"""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import tempfile
import threading
import time
import struct
import shutil

import numpy as np
import onnxruntime as ort

RATE = 44100
SEGMENT = 343980
HOP = 1024
FFT = 4096
STEMS = ('drums', 'bass', 'other', 'vocals')
MODEL_SHA = 'f2c050b7264d2b2401497beb712c26a50e6162dfb951041060f23f84929d600e'
MODEL_BYTES = 52271228
MAX_SECONDS = 3600
MAX_BYTES = 2 * 1024 ** 3
DISK_RESERVE = 128 * 1024 ** 2


class SeparationCancelled(Exception):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise SeparationCancelled('Stem separation cancelled.')


def waveform_to_spectrum(waveform):
    """SCNet rectangular, centered orthonormal STFT and scalar normalization."""
    samples = waveform.shape[-1]
    padding = HOP - samples % HOP
    if (samples + padding) // HOP % 2 == 0:
        padding += HOP
    padded = np.pad(np.asarray(waveform, dtype=np.float32), ((0, 0), (0, padding)))
    padded = np.pad(padded, ((0, 0), (FFT // 2, FFT // 2)), mode='reflect')
    windows = np.lib.stride_tricks.sliding_window_view(padded, FFT, axis=-1)[:, ::HOP]
    spectrum = np.fft.rfft(windows, norm='ortho', axis=-1).astype(np.complex64)
    packed = np.stack((spectrum.real, spectrum.imag), axis=1).transpose(0, 1, 3, 2)
    packed = packed.reshape(1, 4, FFT // 2 + 1, -1)
    mean = float(packed.mean(dtype=np.float64))
    std = float(packed.std(dtype=np.float64, ddof=1))
    return np.asarray((packed - mean) / (1e-5 + std), dtype=np.float32), mean, std, padding


def spectrum_to_waveform(spectrum, mean, std, padding):
    """Reverse the official rectangular STFT with weighted sample counts."""
    spectrum = np.asarray(spectrum, dtype=np.float32) * np.float32(std) + np.float32(mean)
    sources = spectrum.reshape(4, 2, 2, FFT // 2 + 1, -1)
    values = sources[:, :, 0] + 1j * sources[:, :, 1]
    windows = np.fft.irfft(values.transpose(0, 1, 3, 2), n=FFT, norm='ortho').astype(np.float32)
    length = (windows.shape[-2] - 1) * HOP + FFT
    output = np.zeros((4, 2, length), dtype=np.float32)
    counts = np.zeros(length, dtype=np.float32)
    for index in range(windows.shape[-2]):
        start = index * HOP
        output[:, :, start:start + FFT] += windows[:, :, index]
        counts[start:start + FFT] += 1
    output /= np.maximum(counts, 1)[None, None]
    return output[:, :, FFT // 2:length - FFT // 2 - padding]


def _write_header(stream, frames):
    # IEEE float WAV preserves estimated peaks without clipping or changing the
    # relative stem gains. Decode/playback uses the app's existing media tools.
    size = frames * 2 * 4
    stream.write(struct.pack('<4sI4s4sIHHIIHHH4sII4sI', b'RIFF', 50 + size, b'WAVE',
                             b'fmt ', 18, 3, 2, RATE, RATE * 8, 8, 32, 0,
                             b'fact', 4, frames, b'data', size))


class Separator:
    def __init__(self, model_directory=None, ffmpeg='ffmpeg'):
        self.directory = Path(model_directory or Path(__file__).parent / 'stem_models')
        self.ffmpeg = str(ffmpeg)
        self.session = None

    def _load(self, cancel_event):
        if self.session is not None:
            return
        check_cancel(cancel_event)
        try:
            manifest = json.loads((self.directory / 'manifest.json').read_text(encoding='utf-8'))
            metadata = manifest['model']
            name = metadata['file']
            if (manifest.get('license') != 'MIT' or manifest.get('sample_rate') != RATE
                    or manifest.get('segment_samples') != SEGMENT or manifest.get('stems') != list(STEMS)
                    or Path(name).name != name or metadata.get('sha256') != MODEL_SHA
                    or metadata.get('bytes') != MODEL_BYTES):
                raise ValueError('Incompatible stem model.')
            path = self.directory / name
            if path.stat().st_size != MODEL_BYTES:
                raise ValueError('Invalid stem model size.')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != MODEL_SHA:
                raise ValueError('Invalid stem model checksum.')
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError('The stem model is missing or damaged. Reinstall the complete Mac app.') from error
        check_cancel(cancel_event)
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Loading verified bytes disallows ONNX external-data filesystem paths.
        self.session = ort.InferenceSession(data, sess_options=options, providers=['CPUExecutionProvider'])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or inputs[0].name != 'mix_spec' or inputs[0].shape != [1, 4, 2049, 338]
                or inputs[0].type != 'tensor(float)' or len(outputs) != 1
                or outputs[0].name != 'stems_spec' or outputs[0].shape != [1, 4, 4, 2049, 338]):
            self.session = None
            raise ValueError('The bundled stem model has an incompatible interface.')

    def _decode(self, source, target, cancel_event):
        if shutil.disk_usage(target.parent).free < DISK_RESERVE:
            raise ValueError('Free some disk space before separating this recording.')
        command = [self.ffmpeg, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                   '-i', str(source), '-map', '0:a:0',
                   '-vn', '-t', str(MAX_SECONDS + 1), '-ac', '2', '-ar', str(RATE),
                   '-c:a', 'pcm_f32le', '-f', 'f32le', '-y', str(target)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 300
        try:
            while process.poll() is None:
                check_cancel(cancel_event)
                if time.monotonic() > deadline:
                    raise ValueError('Decoding took too long. Try a shorter recording.')
                if shutil.disk_usage(target.parent).free < DISK_RESERVE:
                    raise ValueError('Free some disk space before separating this recording.')
                time.sleep(.05)
            if process.returncode:
                raise ValueError('This file has no readable audio track.')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        check_cancel(cancel_event)
        size = target.stat().st_size
        if size % 8 or not size:
            raise ValueError('This file has no readable audio track.')
        frames = size // 8
        if frames > MAX_SECONDS * RATE:
            raise ValueError('Choose a recording up to one hour long for stem separation.')
        return frames

    def _predict(self, features, cancel_event):
        options, finished = ort.RunOptions(), threading.Event()

        def interrupt():
            while not finished.wait(.05):
                if cancel_event.is_set():
                    options.terminate = True
                    return

        watcher = threading.Thread(target=interrupt, name='BlazeStemCancellation', daemon=True)
        watcher.start()
        try:
            return self.session.run(['stems_spec'], {'mix_spec': features}, options)[0]
        except Exception:
            check_cancel(cancel_event)
            raise
        finally:
            finished.set()
            watcher.join(timeout=1)

    def separate(self, source, output_dir, progress=None, cancel_event=None):
        """Return four stem ID → WAV Path entries; clean partial files on failure.

        The caller must supply an empty private staging directory and publish it
        only after success. Progress receives (fraction, readable message).
        """
        cancel_event = cancel_event or threading.Event()
        progress = progress or (lambda fraction, message: None)
        check_cancel(cancel_event)
        source = Path(source).resolve(strict=True)
        if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
            raise ValueError('Choose an audio or video file smaller than 2 GB.')
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if any(output_dir.iterdir()):
            raise ValueError('Stem separation requires a new empty output folder.')
        paths = {stem: output_dir / (stem + '.wav') for stem in STEMS}
        streams = []
        pcm = None
        try:
            progress(0, 'Opening the offline stem model…')
            self._load(cancel_event)
            with tempfile.TemporaryDirectory(prefix='blaze-stem-') as temporary:
                decoded = Path(temporary) / 'audio.f32'
                progress(.02, 'Reading the recording…')
                frames = self._decode(source, decoded, cancel_event)
                if shutil.disk_usage(output_dir).free < frames * 8 * len(STEMS) + DISK_RESERVE:
                    raise ValueError('There is not enough free space to save four WAV stems.')
                pcm = np.memmap(decoded, mode='r', dtype='<f4', shape=(frames, 2))
                total, square, stereo_square = 0., 0., 0.
                for offset in range(0, frames, SEGMENT):
                    check_cancel(cancel_event)
                    block = np.asarray(pcm[offset:offset + SEGMENT])
                    if not np.isfinite(block).all():
                        raise ValueError('The recording contains invalid audio samples.')
                    mono = block.mean(axis=1, dtype=np.float64)
                    total += float(mono.sum())
                    square += float(np.dot(mono, mono))
                    stereo_square += float(np.square(block, dtype=np.float64).sum())
                mean = total / frames
                deviation = math.sqrt(max(0., (square - frames * mean * mean) / max(1, frames - 1)))
                # Anti-phase stereo can cancel in the mono reference while
                # still containing music. Use stereo energy in that edge case.
                if deviation < 1e-8:
                    deviation = math.sqrt(max(0., stereo_square / (2 * frames) - mean * mean))
                for stem in STEMS:
                    stream = paths[stem].open('wb')
                    streams.append(stream)
                    _write_header(stream, frames)
                stride = SEGMENT // 2
                weight = np.concatenate((np.arange(1, SEGMENT // 2 + 1),
                                         np.arange(SEGMENT - SEGMENT // 2, 0, -1))).astype(np.float32)
                weight /= weight.max()
                accum = np.zeros((4, 2, SEGMENT), dtype=np.float32)
                denominator = np.zeros(SEGMENT, dtype=np.float32)
                for offset in range(0, frames, stride):
                    check_cancel(cancel_event)
                    count = min(SEGMENT, frames - offset)
                    audio = np.zeros((2, SEGMENT), dtype=np.float32)
                    audio[:, :count] = pcm[offset:offset + count].T
                    if deviation > 1e-8:
                        audio[:, :count] = (audio[:, :count] - np.float32(mean)) / np.float32(deviation)
                        features, feature_mean, feature_std, padding = waveform_to_spectrum(audio)
                        prediction = self._predict(features, cancel_event)
                        check_cancel(cancel_event)
                        if prediction.shape != (1, 4, 4, 2049, 338) or not np.isfinite(prediction).all():
                            raise ValueError('The stem model returned invalid audio.')
                        separated = spectrum_to_waveform(prediction[0], feature_mean, feature_std, padding)
                        separated *= np.float32(deviation)
                        separated += np.float32(mean)
                    else:
                        separated = np.zeros((4, 2, SEGMENT), dtype=np.float32)
                        separated[2, :, :count] = audio[:, :count]
                    if separated.shape != (4, 2, SEGMENT) or not np.isfinite(separated).all():
                        raise ValueError('The stem model returned invalid audio.')
                    accum[:, :, :count] += separated[:, :, :count] * weight[:count]
                    denominator[:count] += weight[:count]
                    written = min(stride, frames - offset)
                    block = accum[:, :, :written] / denominator[None, None, :written]
                    for index, stream in enumerate(streams):
                        stream.write(np.asarray(block[index].T, dtype='<f4').tobytes())
                    accum[:, :, :-stride] = accum[:, :, stride:]
                    accum[:, :, -stride:] = 0
                    denominator[:-stride] = denominator[stride:]
                    denominator[-stride:] = 0
                    progress(.05 + .93 * min(1., (offset + written) / frames), 'Separating vocals, drums, bass and other…')
                del pcm
                pcm = None
            check_cancel(cancel_event)
            for stream in streams:
                stream.close()
            streams.clear()
            progress(1, 'Four stems are ready.')
            return paths
        except Exception:
            for stream in streams:
                try:
                    stream.close()
                except OSError:
                    pass
            if pcm is not None:
                del pcm
            for path in paths.values():
                path.unlink(missing_ok=True)
            raise
