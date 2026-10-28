"""Bounded, real stereo envelopes for the local Mac arrangement view.

The display decoder never loads a recording into RAM. It writes a bounded,
low-rate temporary stream, then reduces that stream into at most 1,024 pairs
per channel. The low decode rate describes the envelope, not the source audio.
"""
from collections import OrderedDict
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

import numpy as np

DECODE_RATE = 4000
MAX_SECONDS = 7200
MAX_BYTES = 2 * 1024 ** 3
MAX_PEAKS = 1024
DECODE_TIMEOUT = 90
DISK_RESERVE = 128 * 1024 ** 2


class StaleWaveform(ValueError):
    """The selected recording or separation changed while preparing its view."""


class WaveformBusy(ValueError):
    """Another two waveform requests are already being decoded."""


def selection(studio, revision, job_id='', stem=''):
    """Capture only the current source or a completed stem owned by its session."""
    with studio.lock:
        if revision != str(studio.source_revision):
            raise StaleWaveform('The selected recording changed. Reload its waveform.')
        selected = studio.source
        if selected is None:
            raise ValueError('Open a recording to view its waveform.')
        manager = studio.stems
        snapshot = manager.snapshot() if manager else {}
        owns_job = (snapshot.get('status') == 'done' and
                    (snapshot.get('sourceRevision') == studio.source_revision or
                     selected in manager.files.values()))
        owned_job = snapshot.get('jobId', '') if owns_job else ''
        if job_id or stem:
            if not job_id or not stem or job_id != owned_job:
                raise ValueError('Choose a stem from the selected recording.')
            source = manager.file(job_id, stem)
        else:
            source = selected
        captured_revision = studio.source_revision

    def valid():
        with studio.lock:
            if studio.source_revision != captured_revision or studio.source != selected:
                return False
            if job_id:
                return (studio.stems is manager and manager.value.get('status') == 'done' and
                        manager.value.get('jobId') == job_id and manager.files.get(stem) == source)
            return True

    return source, valid, owned_job


class Waveforms:
    def __init__(self, ffmpeg):
        self.ffmpeg = str(ffmpeg)
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(2)
        self.closed = threading.Event()

    def close(self):
        self.closed.set()
        with self.lock:
            self.cache.clear()

    def _check(self, valid):
        if self.closed.is_set() or not valid():
            raise StaleWaveform('The selected recording changed. Reload its waveform.')

    def get(self, source, valid=lambda: True):
        self._check(valid)
        try:
            path = Path(source)
            stat = path.stat()
            if not path.is_file() or not 0 < stat.st_size <= MAX_BYTES:
                raise ValueError
            identity = (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except (OSError, TypeError, ValueError):
            raise ValueError('Choose a readable local recording smaller than 2 GB.') from None
        with self.lock:
            cached = self.cache.get(identity)
            if cached is not None:
                self.cache.move_to_end(identity)
        if cached is not None:
            self._check(valid)
            return dict(cached)
        if not self.slots.acquire(blocking=False):
            raise WaveformBusy('Waveforms are still loading. Try again shortly.')
        try:
            value = self._decode(path, valid)
            self._check(valid)
            final = path.stat()
            if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != identity[1:]:
                raise StaleWaveform('The recording changed. Reload its waveform.')
            with self.lock:
                self.cache[identity] = value
                self.cache.move_to_end(identity)
                while len(self.cache) > 12:
                    self.cache.popitem(last=False)
            return dict(value)
        except OSError:
            self._check(valid)
            raise ValueError('This recording could not be read for its waveform.') from None
        finally:
            self.slots.release()

    def _decode(self, source, valid):
        with tempfile.TemporaryFile(prefix='blaze-waveform-') as decoded:
            if shutil.disk_usage(tempfile.gettempdir()).free < DISK_RESERVE:
                raise ValueError('Free some disk space before loading the waveform.')
            command = [self.ffmpeg, '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                       '-threads', '1', '-filter_threads', '1', '-i', str(source),
                       '-map', '0:a:0', '-vn', '-t', str(MAX_SECONDS + 1), '-ac', '2',
                       '-ar', str(DECODE_RATE), '-c:a', 'pcm_f32le', '-f', 'f32le', 'pipe:1']
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=decoded,
                                       stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + DECODE_TIMEOUT
            try:
                while process.poll() is None:
                    self._check(valid)
                    if time.monotonic() > deadline:
                        raise ValueError('Loading the waveform took too long. Try a shorter recording.')
                    if decoded.tell() > (MAX_SECONDS + 1) * DECODE_RATE * 8:
                        raise ValueError('Choose a recording up to two hours long.')
                    if shutil.disk_usage(tempfile.gettempdir()).free < DISK_RESERVE:
                        raise ValueError('Free some disk space before loading the waveform.')
                    time.sleep(.025)
                self._check(valid)
                if process.returncode:
                    raise ValueError('This recording has no readable audio track.')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            size = decoded.tell()
            if not size or size % 8:
                raise ValueError('This recording has no readable audio track.')
            frames = size // 8
            if frames > MAX_SECONDS * DECODE_RATE:
                raise ValueError('Choose a recording up to two hours long.')
            count = min(MAX_PEAKS, frames)
            peaks = [[], []]
            decoded.seek(0)
            for index in range(count):
                self._check(valid)
                start = index * frames // count
                end = (index + 1) * frames // count
                block = np.frombuffer(decoded.read((end - start) * 8), dtype='<f4').reshape(-1, 2)
                if not len(block) or not np.isfinite(block).all():
                    raise ValueError('This recording contains invalid audio samples.')
                minimum, maximum = block.min(axis=0), block.max(axis=0)
                for channel in range(2):
                    peaks[channel].append([round(float(minimum[channel]), 6), round(float(maximum[channel]), 6)])
            return {'duration': frames / DECODE_RATE, 'decodeRate': DECODE_RATE,
                    'channels': 2, 'peaks': peaks}
