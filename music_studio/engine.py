"""Offline pretrained BTC inference. Runtime needs only NumPy and ONNX Runtime."""
from pathlib import Path
import hashlib
import json
import math
import struct
import subprocess
import threading
import time
import numpy as np
import onnxruntime as ort
from .chords import estimate_key
from .rhythm import RhythmDetector

RATE = 22050
CHUNK = 108 * 2048
MAX_BYTES = 2 * 1024 ** 3
MAX_SECONDS = 7200


class AnalysisCancelled(Exception):
    pass


class ModelBundle:
    """Validated immutable model assets; no download or remote fallback."""
    def __init__(self, directory=None, selected='powerful'):
        self.directory = Path(directory or Path(__file__).parent / 'models')
        try:
            self.manifest = json.loads((self.directory / 'manifest.json').read_text(encoding='utf-8'))
            self.metadata = self.manifest['models']['extended' if selected == 'powerful' else selected].copy()
        except (OSError, KeyError, ValueError) as error:
            raise ValueError('Recognition model is missing or invalid. Install the complete Music Studio model bundle.') from error
        if self.manifest.get('schema_version') != 1 or self.manifest.get('sample_rate') != RATE or self.manifest.get('timestep') != 108:
            raise ValueError('This model bundle is incompatible with Music Studio.')
        if len(self.metadata['labels']) != self.metadata['classes'] or self.metadata['classes'] not in (25, 170):
            raise ValueError('The recognition vocabulary is invalid.')
        if not math.isfinite(self.metadata['mean']) or not math.isfinite(self.metadata['std']) or self.metadata['std'] <= 0:
            raise ValueError('The model normalization is invalid.')
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.frontend = self._session(self.manifest['frontend'], options)
        self.network = self._session(self.metadata, options)
        self.selected = selected
        self.structured = None
        if selected == 'powerful':
            from .structured import StructuredRecognizer
            self.structured = StructuredRecognizer(self.directory)
            assets = [self.metadata['sha256'], self.structured.manifest['frontend']['sha256'],
                      *(a['sha256'] for a in self.structured.manifest['models'])]
            self.metadata['name'] = 'Blaze Advanced Ensemble'
            self.metadata['version'] = 'structured-1'
            self.metadata['sha256'] = hashlib.sha256(''.join(assets).encode()).hexdigest()

    def _session(self, metadata, options):
        name = metadata['file']
        if Path(name).name != name:
            raise ValueError('Model asset paths must remain inside the bundle.')
        path = self.directory / name
        if not path.is_file() or path.stat().st_size > 700 * 1024 ** 2:
            raise ValueError('Recognition model file is missing or too large.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != metadata['sha256']:
            raise ValueError('Recognition model verification failed. Reinstall or import a verified model bundle.')
        # Bytes prevent ONNX external-data paths from reading arbitrary files.
        return ort.InferenceSession(data, sess_options=options, providers=['CPUExecutionProvider'])

    def predict(self, pcm):
        if pcm.size < 128:
            raise ValueError('This recording is too short for chord recognition.')
        observed = len(pcm)
        if observed < 4410:
            pcm = np.pad(pcm, (0, 4410-observed), mode='edge')
        log_cqt = self.frontend.run(None, {'pcm': np.asarray(pcm, dtype=np.float32)[None]})[0][0]
        normalized = ((log_cqt - self.metadata['mean']) / self.metadata['std']).astype(np.float32)
        features = np.zeros((1, 108, 144), dtype=np.float32)
        valid = min(108, len(normalized), math.ceil(observed / 2048))
        features[0, :valid] = normalized[:valid]
        # Preserve observed spectral values and avoid treating an incomplete
        # final context as average training noise. Padding is never exported.
        if valid < 108:
            features[0, valid:] = normalized[valid - 1]
        logits = self.network.run(None, {'features': features})[0][0, :valid]
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return probabilities


def wav_header(stream):
    def exact(size):
        result = bytearray()
        while len(result) < size:
            data = stream.read(size - len(result))
            if not data:
                raise ValueError('No readable audio track or incomplete decoded audio. Try another file.')
            result.extend(data)
        return bytes(result)
    header = exact(12)
    if header[:4] != b'RIFF' or header[8:] != b'WAVE':
        raise ValueError('The local decoder returned unsupported audio.')
    valid = False
    consumed = 0
    while consumed < 1024 ** 2:
        chunk = exact(8)
        length = struct.unpack('<I', chunk[4:])[0]
        if chunk[:4] == b'data':
            if not valid:
                raise ValueError('The decoded audio format is missing.')
            return
        if length > 1024 ** 2:
            raise ValueError('Invalid decoded audio header.')
        payload = exact(length)
        if chunk[:4] == b'fmt ':
            if len(payload) < 16:
                raise ValueError('Invalid decoded audio format.')
            encoding, channels, rate, _, _, bits = struct.unpack('<HHIIHH', payload[:16])
            valid = (encoding, channels, rate, bits) == (1, 1, RATE, 16)
        if length % 2:
            exact(1)
        consumed += length + 8
    raise ValueError('Invalid decoded audio header.')


def tempo_and_beats(onsets):
    """DSP estimate, not a neural beat model or an asserted exact musical tempo."""
    values = np.asarray(onsets, dtype=np.float64)
    if len(values) < 4 * RATE / 256 or float(values.max(initial=0)) < 1e-7:
        return None, []
    fps = RATE / 256
    # Estimate on a bounded three-minute excerpt; tracking uses the full envelope.
    excerpt = values[:int(180 * fps)].copy()
    excerpt -= excerpt.mean()
    nfft = 1 << (2 * len(excerpt) - 1).bit_length()
    transformed = np.fft.rfft(excerpt, nfft)
    correlation = np.fft.irfft(transformed * transformed.conjugate(), nfft)[:len(excerpt)]
    low, high = math.ceil(fps * 60 / 240), min(len(excerpt) - 2, math.floor(fps * 60 / 40))
    if high <= low or correlation[0] <= 0:
        return None, []
    candidate = max(range(low, high + 1), key=lambda lag: correlation[lag] / max(1, len(excerpt) - lag))
    if correlation[candidate] / correlation[0] < .18:
        return None, []
    a, b, c = correlation[candidate - 1:candidate + 2]
    offset = .5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0
    period = candidate + max(-.5, min(.5, float(offset)))
    bpm = round(60 * fps / period, 1)
    # Track strong local onsets close to the estimated grid, with explicit gaps.
    peaks = np.flatnonzero((values[1:-1] > values[:-2]) & (values[1:-1] >= values[2:])) + 1
    if not len(peaks):
        return bpm, []
    threshold = max(1e-7, float(np.percentile(values[peaks], 60)) * .5)
    beats = []
    for index in peaks:
        if values[index] < threshold:
            continue
        timestamp = float(index / fps)
        if not beats or timestamp - beats[-1] >= .65 * period / fps:
            beats.append(round(timestamp, 4))
    return bpm, beats


def bridge_uncertain_frames(frames, max_gap=.28):
    """Bridge only short X gaps bounded by the same stable recognised chord.

    Silence, differing neighbours and sustained ambiguity remain unchanged.
    No raw probability threshold is lowered.
    """
    i = 0
    while i < len(frames):
        if frames[i]['chord'] != 'X':
            i += 1
            continue
        start = i
        while i < len(frames) and frames[i]['chord'] == 'X':
            i += 1
        if start == 0 or i == len(frames):
            continue
        left, right = frames[start - 1]['chord'], frames[i]['chord']
        if left != right or left in ('X', 'N') or frames[i - 1]['end'] - frames[start]['start'] > max_gap:
            continue
        a, b = start - 1, i
        while a > 0 and frames[a - 1]['chord'] == left:
            a -= 1
        while b + 1 < len(frames) and frames[b + 1]['chord'] == right:
            b += 1
        if frames[start - 1]['end'] - frames[a]['start'] < .2 or frames[b]['end'] - frames[i]['start'] < .2:
            continue
        for frame in frames[start:i]:
            frame['chord'] = left
            frame['model_score'] = None
    return frames


class Analyzer:
    def __init__(self, bundle, ffmpeg):
        self.bundle = bundle
        self.ffmpeg = str(ffmpeg)
        self.cancelled = threading.Event()
        self.process = None

    def cancel(self):
        self.cancelled.set()
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def check(self):
        if self.cancelled.is_set():
            raise AnalysisCancelled()

    def analyze(self, source, progress=lambda message: None):
        structured = self.bundle.structured
        if structured:
            structured.begin()
        try:
            return self._analyze(source, progress)
        finally:
            if structured:
                structured.close()

    def _analyze(self, source, progress=lambda message: None):
        path = Path(source).resolve()
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError('Choose a nonempty local audio or video file.')
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Choose a media file smaller than 2 GB.')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(65536):
                self.check()
                digest.update(block)
        progress('Finding chords locally…')
        rhythm = RhythmDetector(self.bundle.directory) if (self.bundle.directory / 'rhythm_manifest.json').is_file() else None
        command = [self.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-protocol_whitelist', 'file,pipe',
                   '-threads', '2', '-i', str(path), '-map', '0:a:0', '-vn', '-sn', '-dn',
                   '-af', 'aresample=async=1:first_pts=0', '-ac', '1', '-ar', str(RATE), '-c:a', 'pcm_s16le', '-f', 'wav', 'pipe:1']
        started = time.perf_counter()
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.process = process
        frames = []
        onsets = []
        waveform = []
        sample_count = 0
        context_tail = np.empty(0, dtype=np.float32)
        envelope_tail = np.empty(0, dtype=np.float32)
        spectral_tail = np.zeros(1792, dtype=np.float32)
        previous_spectrum = np.zeros(1025, dtype=np.float64)
        try:
            wav_header(process.stdout)
            while True:
                self.check()
                read_samples = CHUNK if sample_count == 0 else CHUNK // 2
                data = bytearray()
                while len(data) < read_samples * 2:
                    block = process.stdout.read(read_samples * 2 - len(data))
                    self.check()
                    if not block:
                        break
                    data.extend(block)
                if not data:
                    break
                if len(data) % 2:
                    raise ValueError('The decoded audio stream is incomplete.')
                pcm = np.frombuffer(data, dtype='<i2').astype(np.float32) / 32768
                start_sample = sample_count - len(context_tail)
                sample_count += len(pcm)
                new_pcm = pcm
                if rhythm:
                    rhythm.audio.feed(new_pcm)
                if self.bundle.structured:
                    self.bundle.structured.feed(new_pcm)
                pcm = np.concatenate((context_tail, new_pcm))
                context_tail = pcm[-CHUNK//2:].copy()
                if sample_count / RATE > MAX_SECONDS:
                    raise ValueError('Choose media shorter than two hours.')
                envelope = np.concatenate((envelope_tail, new_pcm))
                complete = len(envelope) // 256 * 256
                envelope_tail = envelope[complete:].copy()
                blocks = envelope[:complete].reshape(-1, 256)
                if len(blocks):
                    spectral_signal = np.concatenate((spectral_tail, blocks.reshape(-1)))
                    windows = np.lib.stride_tricks.sliding_window_view(spectral_signal, 2048)[::256]
                    spectrum = np.abs(np.fft.rfft(windows * np.hanning(2048), axis=1))
                    preceding = np.vstack((previous_spectrum, spectrum[:-1]))
                    flux = np.maximum(0, spectrum - preceding).sum(axis=1) / np.maximum(1e-8, spectrum.sum(axis=1))
                    onsets.extend(np.maximum(0, flux - .05).tolist())
                    spectral_tail = spectral_signal[-1792:].copy()
                    previous_spectrum = spectrum[-1]
                for block in blocks:
                    waveform.append(float(np.max(np.abs(block))))
                if len(pcm) < 128:
                    probabilities = None
                else:
                    probabilities = self.bundle.predict(pcm)
                frame_count = len(probabilities) if probabilities is not None else math.ceil(len(pcm)/2048)
                for index in range(frame_count):
                    global_index = start_sample // 2048 + index
                    start = global_index * 2048 / RATE
                    if start >= sample_count / RATE:
                        break
                    end = min(sample_count / RATE, (global_index + 1) * 2048 / RATE)
                    while len(frames) <= global_index:
                        frames.append({'start': start, 'end': end, 'chord': 'X', 'model_score': 0., 'edited': False, '_prob': np.zeros(self.bundle.metadata['classes'],dtype=np.float32), '_weight': 0., '_silent': True})
                    frame = frames[global_index]
                    frame['end'] = end
                    left, right = max(0,index*2048-4096), min(len(pcm),index*2048+4096)
                    frame['_silent'] &= float(np.max(np.abs(pcm[left:right]),initial=0)) < 1e-5
                    if probabilities is not None:
                        weight = max(.05,min(index+1,frame_count-index,27)/27)
                        frame['_prob'] += probabilities[index] * weight
                        frame['_weight'] += weight
                progress(f'Finding chords locally · {sample_count / RATE:.1f} seconds analysed')
                if len(data) < read_samples * 2:
                    break
            self.check()
            if process.wait() != 0 or not sample_count:
                raise ValueError('No readable audio track. Try another file.')
        finally:
            if process.poll() is None:
                process.terminate()
            process.stdout.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            self.process = None
        baseline_probabilities = [] if self.bundle.structured else None
        for frame in frames:
            probability = frame.pop('_prob') / max(frame.pop('_weight'),1e-8)
            if baseline_probabilities is not None:
                baseline_probabilities.append(probability)
            ranked = np.argsort(probability)[-2:]
            selected = int(ranked[-1]); score = float(probability[selected])
            label = self.bundle.metadata['labels'][selected]
            if label != 'N' and (score < .35 or score - float(probability[ranked[-2]]) < .04):
                label = 'X'
            if frame.pop('_silent'):
                label, score = 'N', 0.
            frame['chord'], frame['model_score'] = label, score
        rhythm_result = rhythm.finish(sample_count / RATE, self.check, progress) if rhythm else {}
        if self.bundle.structured:
            recognizer = self.bundle.structured
            try:
                self.check();progress('Reading harmony and tuning locally…')
                features, decoded_audio = recognizer.features()
                try:
                    heads = recognizer.predict_features(features, self.check, progress)
                    frames = recognizer.decode(heads, np.asarray(baseline_probabilities), self.bundle.manifest['models']['extended']['labels'],
                                               sample_count / RATE, rhythm_result.get('beats', []), decoded_audio, self.check)
                finally:
                    del decoded_audio
            finally:
                recognizer.close()
        # Three-frame voting only removes isolated flips; extensions remain model labels.
        labels = [frame['chord'] for frame in frames]
        for i in range(1, len(frames) - 1):
            if labels[i - 1] == labels[i + 1] and labels[i] != 'N':
                frames[i]['chord'] = labels[i - 1]
                if labels[i] != labels[i - 1]:
                    frames[i]['model_score'] = None
        bridge_uncertain_frames(frames)
        events = []
        for frame in frames:
            if events and events[-1]['chord'] == frame['chord']:
                event = events[-1]
                old_duration = event['end'] - event['start']
                new_duration = frame['end'] - frame['start']
                event['model_score'] = ((event['model_score'] * old_duration + frame['model_score'] * new_duration) / (old_duration + new_duration)
                                        if event['model_score'] is not None and frame['model_score'] is not None else None)
                event['end'] = frame['end']
            else:
                events.append(dict(frame))
        if waveform:
            width = min(1024, len(waveform))
            boundaries = np.linspace(0, len(waveform), width + 1, dtype=int)
            peaks = [max(waveform[left:right]) for left, right in zip(boundaries, boundaries[1:])]
        else:
            peaks = [float(np.max(np.abs(envelope_tail), initial=0))]
        bpm, beats = tempo_and_beats(onsets)
        if rhythm:
            bpm, beats = rhythm_result['tempo_bpm'], rhythm_result['beats']
        metadata = self.bundle.metadata
        return {'schema_version': 1, 'engine_version': 'structured1' if self.bundle.structured else 'overlap1', 'audio_file': path.name, 'source_sha256': digest.hexdigest(),
                'duration': sample_count / RATE, 'key': estimate_key(events), 'tempo_bpm': bpm, 'beats': beats,
                'waveform': peaks, 'model': {'name': metadata['name'], 'version': metadata['version'],
                'sha256': metadata['sha256'], 'frontend_sha256': self.bundle.manifest['frontend']['sha256']},
                'confidence_kind': 'uncalibrated_model_score', 'chords': events,
                'analysis_seconds': round(time.perf_counter() - started, 3), **rhythm_result}
