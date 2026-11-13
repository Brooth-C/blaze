"""One background separation worker with retained completed Studio sessions."""
from pathlib import Path
from contextlib import suppress
import shutil
import json
import os
import re
import time
import subprocess
import sys
import threading
import uuid

STEMS = ('drums', 'bass', 'other', 'vocals')
OUTPUTS = {'stems': STEMS, 'piano': ('piano', 'accompaniment'),
           'five': ('vocals', 'drums', 'bass', 'piano', 'other'),
           'nine': ('vocals', 'drums', 'bass', 'piano', 'guitar', 'strings', 'brass', 'synths', 'other')}


class StemJobs:
    def __init__(self, studio, model_directory=None, separator_factory=None):
        self.studio = studio
        self.models = Path(model_directory or Path(__file__).parent / 'stem_models')
        self.root = studio.directory / 'Stems'
        self.separator_factory = separator_factory
        self.worker = None
        self.cancel_event = threading.Event()
        self.closed = False
        self.files = {}
        self.sessions = {}
        self._selection = None
        self.value = {'status': 'idle', 'progress': 0, 'message': '', 'error': None,
                      'jobId': '', 'sourceRevision': 0, 'sourceName': '', 'stems': []}
        self._load_sessions()

    def snapshot(self):
        with self.studio.lock:
            return dict(self.value, available=bool(self.separator_factory or
                        (self.models / 'manifest.json').is_file()),
                        stems=[dict(row) for row in self.value['stems']],
                        sessions=[self._session_snapshot(row) for row in reversed(list(self.sessions.values()))])

    @staticmethod
    def _session_snapshot(session):
        value = session['value']
        return dict(value, stems=[dict(row) for row in value['stems']],
                    original=dict(value['original']))

    @staticmethod
    def _identity_key(value):
        if (not isinstance(value, (list, tuple)) or len(value) != 5 or
                not isinstance(value[0], str) or len(value[0]) > 8192 or
                '\0' in value[0] or not Path(value[0]).is_absolute() or
                any(type(part) is not int for part in value[1:]) or
                not 0 < value[3] <= 2 * 1024 ** 3):
            raise ValueError('Invalid original recording identity.')
        return tuple(value)

    @staticmethod
    def _text(value, filename=False):
        if not isinstance(value, str) or not 0 < len(value) <= 4096 or '\0' in value:
            raise ValueError('Invalid saved recording name.')
        if filename and ('/' in value or '\\' in value or value in ('.', '..')):
            raise ValueError('Invalid saved recording filename.')
        return value

    @staticmethod
    def _owned_file(directory, relative, original=False):
        if (not isinstance(relative, str) or not relative or '\\' in relative or
                Path(relative).is_absolute() or
                any(part in ('', '.', '..') for part in relative.split('/'))):
            raise ValueError('Invalid saved recording path.')
        path = (directory / relative).resolve(strict=True)
        path.relative_to(directory)
        if not path.is_file() or not (0 if original else 44) < path.stat().st_size <= 2 * 1024 ** 3:
            raise ValueError('The saved track is missing or incomplete.')
        return path

    def _persist_session(self, identity, session):
        directory = session['directory']
        value = session['value']
        record = {'schema_version': 1, 'jobId': identity, 'mode': value['mode'],
                  'sourceName': value['sourceName'], 'sourceIdentity': list(session['source_key']),
                  'createdAt': value['createdAt'], 'original': dict(value['original']),
                  'originalStamp': list(session['original_stamp']),
                  'files': {stem: str(path.resolve().relative_to(directory))
                            for stem, path in session['files'].items()}}
        temporary = directory / ('.session-' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('x', encoding='utf-8') as stream:
                json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(directory / 'session.json')
        finally:
            temporary.unlink(missing_ok=True)

    def _load_sessions(self):
        """Recover complete, owned output sets; ignore partial or invalid records."""
        if not self.root.is_dir():
            return
        recovered = []
        try:
            folders = list(self.root.iterdir())
        except OSError:
            return
        for folder in folders:
            try:
                if (not re.fullmatch(r'[0-9a-f]{32}', folder.name) or folder.is_symlink() or
                        not folder.is_dir()):
                    continue
                directory = folder.resolve(strict=True)
                if directory.parent != self.root.resolve():
                    continue
                sidecar = directory / 'session.json'
                if sidecar.is_symlink() or not 0 < sidecar.stat().st_size <= 65536:
                    continue
                record = json.loads(sidecar.read_text(encoding='utf-8'))
                if not isinstance(record, dict):
                    continue
                identity, mode = folder.name, record.get('mode')
                if (record.get('schema_version') != 1 or record.get('jobId') != identity or
                        not isinstance(mode, str) or mode not in OUTPUTS):
                    continue
                source_key = self._identity_key(record.get('sourceIdentity'))
                source_name = self._text(record.get('sourceName'))
                original = record.get('original')
                if not isinstance(original, dict) or original.get('id') != 'source':
                    continue
                filename = self._text(original.get('filename'), filename=True)
                files = record.get('files')
                if not isinstance(files, dict) or set(files) != set(OUTPUTS[mode]) | {'source'}:
                    continue
                paths = {stem: self._owned_file(directory, relative, stem == 'source')
                         for stem, relative in files.items()}
                if len(set(paths.values())) != len(paths):
                    continue
                original_stamp = record.get('originalStamp')
                stat = paths['source'].stat()
                if (not isinstance(original_stamp, list) or len(original_stamp) != 2 or
                        any(type(part) is not int for part in original_stamp) or
                        tuple(original_stamp) != (stat.st_size, stat.st_mtime_ns)):
                    continue
                kind = 'video' if paths['source'].suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v') else 'audio'
                if original.get('mediaKind') != kind:
                    continue
                created = record.get('createdAt')
                if type(created) is not int or not 0 <= created < 2 ** 53:
                    continue
                value = {'jobId': identity, 'sourceName': source_name, 'sourceRevision': None,
                         'mode': mode, 'createdAt': created,
                         'stems': [{'id': stem, 'label': stem.title(), 'filename': stem.title() + '.wav'}
                                   for stem in OUTPUTS[mode]],
                         'original': {'id': 'source', 'label': 'Original', 'filename': filename,
                                      'mediaKind': kind}}
                recovered.append((created, identity, {'value': value, 'files': paths,
                                  'source': Path(source_key[0]), 'sourceRevision': None,
                                  'source_key': source_key, 'directory': directory,
                                  'original_stamp': tuple(original_stamp)}))
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                continue
        for _, identity, session in sorted(recovered, key=lambda row: (row[0], row[1])):
            self.sessions[identity] = session
            self.studio.associate_source_identity(session['source_key'], session['files']['source'])
        if self.sessions:
            latest = next(reversed(self.sessions.values()))
            self.files = latest['files']
            restored = {key: latest['value'][key] for key in ('jobId', 'sourceName', 'sourceRevision', 'mode', 'stems')}
            self.value.update(restored, status='done', progress=1,
                              message='Your saved tracks are ready.', error=None)

    def recording_identity(self, identity):
        """Private logical identity of the original behind a completed separation."""
        with self.studio.lock:
            self.file(identity, 'source')
            session = self.sessions[identity]
            return session.get('source_key') or self.studio.source_identity(session['source'])

    def recording_source(self, identity):
        return self.file(identity, 'source')

    def selected_job(self):
        """Prefer explicit selections, then current-input aliases and known files."""
        with self.studio.lock:
            if self.studio.source is None:
                return ''
            try:
                selected = self.studio.source.resolve()
                if self._selection:
                    identity, revision, path = self._selection
                    if (revision == self.studio.source_revision and selected == path and
                            identity in self.sessions):
                        return identity
                current_key = self.studio.source_identity(selected)
                sessions = list(reversed(list(self.sessions.items())))
                for identity, session in sessions:
                    if (session['sourceRevision'] == self.studio.source_revision and
                            session['source'].resolve() == selected and
                            (not session.get('source_key') or session['source_key'] == current_key)):
                        return identity
                for identity, session in sessions:
                    if any(path.resolve() == selected for path in session['files'].values()):
                        return identity
                for identity, session in sessions:
                    if session.get('source_key') == current_key:
                        return identity
            except (OSError, RuntimeError):
                pass
            return ''

    def selected_stem(self):
        with self.studio.lock:
            identity = self.selected_job()
            if not identity:
                return ''
            session = self.sessions[identity]
            try:
                selected = self.studio.source.resolve()
                saved = next((stem for stem, path in session['files'].items()
                              if path.resolve() == selected), '')
                if saved:
                    return saved
                if (session.get('source_key') == self.studio.source_identity(selected) or
                        (session['sourceRevision'] == self.studio.source_revision and
                         session['source'].resolve() == selected)):
                    return 'source'
            except (OSError, RuntimeError):
                pass
            return ''

    def descriptor(self, identity, stem):
        """Public, path-free metadata for one registered completed file."""
        with self.studio.lock:
            self.file(identity, stem)
            value = self.sessions[identity]['value']
            if stem == 'source':
                return dict(value['original'])
            return dict(next(row for row in value['stems'] if row['id'] == stem))

    def start(self, mode="stems"):
        with self.studio.lock:
            if self.closed or (self.worker and self.worker.is_alive()):
                raise ValueError('Finish or cancel the current task first.')
            if not isinstance(mode, str) or mode not in OUTPUTS:
                raise ValueError('Choose stem separation or piano isolation.')
            expected = OUTPUTS[mode]
            source = self.studio.source
            if source is None or not source.is_file():
                raise ValueError('Open an audio or video recording first.')
            if not self.snapshot()['available']:
                raise ValueError('The stem model is missing. Reinstall the complete Mac app.')
            identity = uuid.uuid4().hex
            self.root.mkdir(parents=True, exist_ok=True)
            pending = self.root / ('.' + identity)
            final = self.root / identity
            pending.mkdir()
            input_path = self.root / ('.' + identity + '.input')
            input_stream = None
            try:
                input_stream = source.open('rb')
                input_stat = os.fstat(input_stream.fileno())
                source_key = self.studio.source_identity(source, input_stat)
                input_stamp = (input_stat.st_dev, input_stat.st_ino, input_stat.st_size, input_stat.st_mtime_ns)
            except OSError:
                if input_stream is not None:
                    input_stream.close()
                pending.rmdir()
                raise ValueError('The recording could not be opened.') from None
            self.cancel_event = threading.Event()
            cancel = self.cancel_event
            source_revision, source_name = self.studio.source_revision, self.studio.name
            self.value.update(status='running', progress=0, message='Preparing your recording…',
                              error=None, jobId=identity, sourceRevision=source_revision,
                              sourceName=source_name, mode=mode, stems=[])

            def progress(fraction, message):
                with self.studio.lock:
                    if not cancel.is_set():
                        self.value.update(progress=max(0, min(1, float(fraction))), message=str(message))

            def run():
                activity = process_info = None
                try:
                    if sys.platform == 'darwin':
                        from Foundation import (NSThread, NSQualityOfServiceUtility, NSProcessInfo,
                                                NSActivityUserInitiatedAllowingIdleSystemSleep)
                        NSThread.currentThread().setQualityOfService_(NSQualityOfServiceUtility)
                        process_info = NSProcessInfo.processInfo()
                        activity = process_info.beginActivityWithOptions_reason_(
                            NSActivityUserInitiatedAllowingIdleSystemSleep, 'Separating audio stems')
                    # Pin the selected recording before returning to the UI. An
                    # imported source may be unlinked when another file opens.
                    # Copy on this worker so a large recording never blocks UI.
                    with input_stream, input_path.open('xb') as copied:
                        total = 0
                        while not cancel.is_set():
                            block = input_stream.read(1024 * 1024)
                            if not block:
                                break
                            total += len(block)
                            if total > 2 * 1024 ** 3:
                                raise ValueError('Choose a recording smaller than 2 GB.')
                            if shutil.disk_usage(self.root).free < 128 * 1024 ** 2:
                                raise ValueError('Free more storage before splitting this recording.')
                            copied.write(block)
                        final_input = os.fstat(input_stream.fileno())
                        if not cancel.is_set() and input_stamp != (final_input.st_dev, final_input.st_ino, final_input.st_size, final_input.st_mtime_ns):
                            raise ValueError('The recording changed while preparing it. Open the recording again.')
                    if cancel.is_set():
                        return
                    if self.separator_factory:
                        separator = self.separator_factory(self.models, self.studio.ffmpeg)
                    elif mode == 'stems' and os.environ.get('BLAZE_EXPERIMENTAL_SCNET_DIR'):
                        from .native_scnet import NativeSCNetSeparator
                        separator = NativeSCNetSeparator(os.environ['BLAZE_EXPERIMENTAL_SCNET_DIR'], self.studio.ffmpeg)
                    else:
                        from .stems import Separator
                        from .native_piano import NativePianoSeparator
                        from .roformer import QualityFiveStemSeparator
                        from .instruments import NineStemSeparator
                        implementation = {'piano': NativePianoSeparator, 'five': QualityFiveStemSeparator,
                                          'nine': NineStemSeparator, 'stems': Separator}[mode]
                        if mode == 'piano':
                            from .piano_backend import selected_piano_backend
                            backend = selected_piano_backend()
                            if backend == 'mlx':
                                from .mlx_piano import MlxPianoSeparator
                                implementation = MlxPianoSeparator
                        if mode == 'piano' and backend == 'onnx':
                            separator = implementation(self.models, self.studio.ffmpeg, runtime_backend='cpu')
                        else:
                            separator = implementation(self.models, self.studio.ffmpeg)
                    outputs = separator.separate(input_path, pending, progress=progress, cancel_event=cancel)
                    if cancel.is_set():
                        return
                    if set(outputs) != set(expected):
                        raise ValueError('Stem separation did not produce all requested tracks.')
                    if len({Path(outputs[name]).resolve() for name in expected}) != len(expected):
                        raise ValueError('Stem separation did not produce distinct saved tracks.')
                    for name in expected:
                        path = Path(outputs[name]).resolve()
                        if path.parent != pending.resolve() or not path.is_file() or path.stat().st_size <= 44:
                            raise ValueError('A separated track could not be saved.')
                    with self.studio.lock:
                        if cancel.is_set() or self.closed:
                            return
                        original = pending / 'original'
                        original.mkdir()
                        original_name = 'Recording' + source.suffix.lower()
                        input_path.rename(original / original_name)
                        pending.rename(final)
                        files = {name: (final / Path(outputs[name]).name).resolve() for name in expected}
                        files['source'] = (final / 'original' / original_name).resolve()
                        video = source.suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v')
                        metadata = {key: self.value[key] for key in ('jobId', 'sourceName', 'sourceRevision', 'mode')}
                        download_name = source_name.replace('/', '_').replace('\\', '_')
                        if source.suffix and Path(download_name).suffix.lower() != source.suffix.lower():
                            download_name += source.suffix.lower()
                        metadata.update(createdAt=time.time_ns() // 1000000,
                                        stems=[{'id': name, 'label': name.title(), 'filename': name.title() + '.wav'}
                                               for name in expected],
                                        original={'id': 'source', 'label': 'Original', 'filename': download_name,
                                                  'mediaKind': 'video' if video else 'audio'})
                        original_stat = files['source'].stat()
                        session = {'value': metadata, 'files': files, 'source': source,
                                   'sourceRevision': source_revision, 'source_key': source_key,
                                   'directory': final.resolve(),
                                   'original_stamp': (original_stat.st_size, original_stat.st_mtime_ns)}
                        self._persist_session(identity, session)
                        self.files = files
                        self.studio.associate_source_identity(source_key, files['source'])
                        self.sessions[identity] = session
                        if self.studio.source_revision == source_revision:
                            self._selection = None
                        published = {key: metadata[key] for key in ('jobId', 'sourceName', 'sourceRevision', 'mode', 'stems')}
                        self.value.update(published, status='done', progress=1,
                                          message={'piano': 'Your piano track is ready.', 'five': 'Your five stems are ready.',
                                                   'nine': 'Your nine stems are ready.', 'stems': 'Your four stems are ready.'}[mode],
                                          error=None)
                except Exception as error:
                    with self.studio.lock:
                        if not cancel.is_set():
                            self.value.update(status='failed', error=str(error) or 'Could not split this recording.',
                                              message='Stem separation could not finish.')
                finally:
                    with suppress(OSError):
                        input_stream.close()
                    with suppress(OSError):
                        input_path.unlink(missing_ok=True)
                    shutil.rmtree(pending, ignore_errors=True)
                    if activity is not None:
                        process_info.endActivity_(activity)
                    with self.studio.lock:
                        if cancel.is_set() and self.value['status'] != 'done':
                            self.value.update(status='cancelled', message='Separation cancelled.', error=None, stems=[])

            try:
                self.worker = threading.Thread(target=run, name='BlazeStemSeparation', daemon=True)
                self.worker.start()
            except Exception:
                input_stream.close()
                shutil.rmtree(pending, ignore_errors=True)
                self.worker = None
                self.value.update(status='failed', error='The background worker could not start.',
                                  message='Try separating this recording again.')
                raise ValueError('The background worker could not start. Try again.') from None
            return self.snapshot()

    def cancel(self):
        with self.studio.lock:
            if self.value['status'] == 'running':
                self.cancel_event.set()
                self.value['message'] = 'Cancelling separation…'
        return self.snapshot()

    def file(self, identity, stem):
        with self.studio.lock:
            if not isinstance(identity, str) or not isinstance(stem, str):
                raise ValueError('Choose a completed track from a saved separation.')
            session = self.sessions.get(identity)
            if session is None or stem not in session['files']:
                raise ValueError('Choose a completed track from a saved separation.')
            source = session['files'][stem]
            if session.get('directory') is not None:
                try:
                    source = source.resolve(strict=True)
                    source.relative_to(session['directory'])
                except (OSError, ValueError, RuntimeError):
                    raise ValueError('The saved track is missing.') from None
            if not source.is_file():
                raise ValueError('The saved track is missing.')
            if stem == 'source' and session.get('original_stamp') is not None:
                stat = source.stat()
                if session['original_stamp'] != (stat.st_size, stat.st_mtime_ns):
                    raise ValueError('The saved original changed. Open it as a new recording.')
            return source

    def select(self, identity, stem, source_revision=None):
        with self.studio.lock:
            if source_revision is not None and (type(source_revision) is not int or
                                                source_revision != self.studio.source_revision):
                raise ValueError('The selected recording changed. Choose a listening mode again.')
            source = self.file(identity, stem)
            description = self.descriptor(identity, stem)
            self.studio.select_source(source, description['filename'])
            self._selection = (identity, self.studio.source_revision, source.resolve())

    def open_folder(self, identity):
        # The original always lives directly below the completed session.
        folder = self.file(identity, 'source').parent.parent
        if sys.platform != 'darwin':
            raise ValueError('Open the Mac app to reveal the saved stems.')
        subprocess.Popen(['/usr/bin/open', str(folder)])

    def close(self):
        with self.studio.lock:
            self.closed = True
        self.cancel()
        if self.worker:
            self.worker.join(timeout=30)
