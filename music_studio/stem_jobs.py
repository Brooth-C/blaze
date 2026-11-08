"""One background separation worker with retained completed Studio sessions."""
from pathlib import Path
from contextlib import suppress
import shutil
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
        self.value = {'status': 'idle', 'progress': 0, 'message': '', 'error': None,
                      'jobId': '', 'sourceRevision': 0, 'sourceName': '', 'stems': []}

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

    def selected_job(self):
        """Resolve the active recording to a completed session without names."""
        with self.studio.lock:
            if self.studio.source is None:
                return ''
            try:
                selected = self.studio.source.resolve()
                sessions = list(reversed(list(self.sessions.items())))
                # A newly separated source can itself be a stem from an older
                # session. Its exact source revision belongs to the newer job.
                for identity, session in sessions:
                    if (session['sourceRevision'] == self.studio.source_revision and
                            session['source'].resolve() == selected):
                        return identity
                for identity, session in sessions:
                    if any(path.resolve() == selected for path in session['files'].values()):
                        return identity
            except (OSError, RuntimeError):
                pass
            return ''

    def selected_stem(self):
        """Identify the saved output by its path, never its display name."""
        with self.studio.lock:
            identity = self.selected_job()
            if not identity:
                return ''
            session = self.sessions[identity]
            try:
                selected = self.studio.source.resolve()
                if (session['sourceRevision'] == self.studio.source_revision and
                        session['source'].resolve() == selected):
                    return 'source'
                return next((stem for stem, path in session['files'].items()
                             if path.resolve() == selected), '')
            except (OSError, RuntimeError):
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
            try:
                source_key = self.studio.source_identity(source)
                input_stream = source.open('rb')
            except OSError:
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
                    if cancel.is_set():
                        return
                    if self.separator_factory:
                        separator = self.separator_factory(self.models, self.studio.ffmpeg)
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
                        self.files = {name: final / Path(outputs[name]).name for name in expected}
                        self.files['source'] = final / 'original' / original_name
                        self.studio.associate_source_identity(source_key, self.files['source'])
                        self.value.update(status='done', progress=1, message={'piano': 'Your piano track is ready.', 'five': 'Your five stems are ready.',
                                                   'nine': 'Your nine stems are ready.', 'stems': 'Your four stems are ready.'}[mode],
                                          stems=[{'id': name, 'label': name.title(),
                                                  'filename': name.title() + '.wav'} for name in expected])
                        video = source.suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v')
                        metadata = {key: self.value[key] for key in ('jobId', 'sourceName', 'sourceRevision', 'mode')}
                        download_name = source_name
                        if source.suffix and Path(download_name).suffix.lower() != source.suffix.lower():
                            download_name += source.suffix.lower()
                        metadata.update(stems=[dict(row) for row in self.value['stems']],
                                        original={'id': 'source', 'label': 'Original', 'filename': download_name,
                                                  'mediaKind': 'video' if video else 'audio'})
                        self.sessions[identity] = {'value': metadata, 'files': self.files,
                                                   'source': source, 'sourceRevision': source_revision}
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
            if not source.is_file():
                raise ValueError('The saved track is missing.')
            return source

    def select(self, identity, stem):
        with self.studio.lock:
            source = self.file(identity, stem)
            description = self.descriptor(identity, stem)
            self.studio.select_source(source, description['filename'])

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
