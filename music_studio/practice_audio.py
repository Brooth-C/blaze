"""Bounded background pitch renders and exports of registered Practice audio."""
import hashlib
import json
import shutil
import subprocess
import threading
import time
import uuid
import zipfile

from .practice_sessions import fingerprint

LIMIT = 512 * 1024 * 1024


class PracticeAudio:
    def __init__(self, studio):
        self.studio = studio
        self.root = studio.directory / 'Practice' / 'audio'
        self.root.mkdir(parents=True, exist_ok=True)
        for old in self.root.iterdir():
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old, ignore_errors=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.worker = None
        self.closed = threading.Event()

    def request(self, body):
        semitones = body.get('semitones', 0)
        kind = body.get('kind', 'source')
        if type(semitones) is not int or not -12 <= semitones <= 12 or kind not in ('source', 'piano', 'backing', 'both'):
            raise ValueError('Choose a pitch between −12 and +12 semitones and a valid track.')
        with self.studio.lock:
            if type(body.get('sourceRevision')) is not int or body['sourceRevision'] != self.studio.source_revision:
                raise ValueError('The recording changed. Try again.')
            manager = self.studio.stems
            job = body.get('jobId')
            if job:
                names = ('piano', 'accompaniment') if kind == 'both' else ({'backing': 'accompaniment'}.get(kind, kind),)
                sources = [(name, manager.file(job, name)) for name in names]
            elif kind == 'source' and self.studio.source:
                sources = [('source', self.studio.source)]
            else:
                raise ValueError('Prepare the piano and backing tracks first.')
            stamps = [fingerprint(path) for _, path in sources]
        key = hashlib.sha256(json.dumps([stamps, semitones, kind]).encode()).hexdigest()
        with self.lock:
            if self.closed.is_set():
                raise ValueError('Practice audio is closing.')
            for identity, row in self.jobs.items():
                if row['key'] == key and row['status'] in ('pending', 'ready'):
                    if row['status'] == 'pending' or row['path'].is_file():
                        return self.status(identity)
                    row.update(status='expired', error='Prepare this export again.')
            if self.worker and self.worker.is_alive():
                raise ValueError('An audio export is already running. You can keep listening.')
            identity = uuid.uuid4().hex
            self.jobs[identity] = {'key': key, 'status': 'pending', 'error': '', 'path': None,
                                   'filename': 'Piano-and-Backing' + (f' ({semitones:+d})' if semitones else '') + '.zip' if kind == 'both' else
                                   {'source': 'Recording', 'piano': 'Piano', 'backing': 'Backing'}[kind] +
                                   (f' ({semitones:+d})' if semitones else '') + '.wav'}
            for old in list(self.jobs)[:-16]:
                del self.jobs[old]
            self.worker = threading.Thread(target=self._render, args=(identity, sources, stamps, semitones, kind),
                                           name='BlazePracticeAudio', daemon=True)
            try:
                self.worker.start()
            except RuntimeError:
                self.worker = None
                self.jobs[identity].update(status='failed', error='The audio worker could not start.')
                raise ValueError('The audio worker could not start. Try again.') from None
            return self.status(identity)

    def _render(self, identity, sources, stamps, semitones, kind):
        row = self.jobs[identity]
        folder = self.root / identity
        try:
            folder.mkdir()
            files = []
            for (name, source), stamp in zip(sources, stamps):
                if self.closed.is_set() or fingerprint(source) != stamp:
                    raise ValueError('The recording changed or the export was cancelled.')
                target = folder / ({'source': 'Recording', 'piano': 'Piano', 'accompaniment': 'Backing'}[name] + '.wav')
                if semitones == 0 and source.suffix.lower() == '.wav':
                    if source.stat().st_size > LIMIT:
                        raise ValueError('This recording is too large to export here.')
                    shutil.copyfile(source, target)
                else:
                    ratio = 2 ** (semitones / 12)
                    filters = f'aresample=44100,asetrate={44100 * ratio:.10f},aresample=44100,atempo={1 / ratio:.10f}'
                    process = subprocess.Popen([str(self.studio.ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(source),
                        '-vn', '-af', filters, '-c:a', 'pcm_f32le', '-fs', str(LIMIT), str(target)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    deadline = time.monotonic() + 900
                    try:
                        while process.poll() is None:
                            if self.closed.wait(.1) or time.monotonic() > deadline:
                                raise ValueError('Audio export cancelled or took too long.')
                        if process.returncode or not target.is_file() or target.stat().st_size <= 44 or target.stat().st_size >= LIMIT:
                            raise ValueError('Could not prepare this audio export.')
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait()
                if fingerprint(source) != stamp:
                    raise ValueError('The recording changed during export.')
                files.append(target)
            target = files[0]
            if kind == 'both':
                target = folder / 'Piano-and-Backing.zip'
                with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
                    for path in files:
                        archive.write(path, path.name)
                for path in files:
                    path.unlink()
            with self.lock:
                row.update(status='ready', path=target)
                # Bound disk retention; never remove the just-published export.
                for old in sorted(self.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[4:]:
                    if old.is_dir():
                        shutil.rmtree(old, ignore_errors=True)
                for old in self.jobs.values():
                    if old['status'] == 'ready' and not old['path'].is_file():
                        old.update(status='expired', error='Prepare this export again.')
        except (OSError, ValueError, subprocess.SubprocessError):
            with self.lock:
                row.update(status='failed', error='Could not prepare audio. Try again or choose a shorter recording.')
            shutil.rmtree(folder, ignore_errors=True)

    def status(self, identity):
        with self.lock:
            row = self.jobs.get(identity)
            if row is None:
                raise ValueError('Audio request expired.')
            return {'requestId': identity, 'status': row['status'], 'error': row['error'], 'filename': row['filename']}

    def file(self, identity):
        with self.lock:
            row = self.jobs.get(identity)
            if not row or row['status'] != 'ready' or not row['path'].is_file():
                raise ValueError('Audio export is not ready.')
            return row['path'], row['filename']

    def close(self):
        self.closed.set()
        if self.worker:
            self.worker.join(timeout=5)
