"""One local stem-separation job, owned by the current Studio session."""
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import uuid

STEMS = ('drums', 'bass', 'other', 'vocals')


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
        self.value = {'status': 'idle', 'progress': 0, 'message': '', 'error': None,
                      'jobId': '', 'sourceRevision': 0, 'sourceName': '', 'stems': []}

    def snapshot(self):
        with self.studio.lock:
            return dict(self.value, available=bool(self.separator_factory or
                        (self.models / 'manifest.json').is_file()),
                        stems=[dict(row) for row in self.value['stems']])

    def start(self):
        with self.studio.lock:
            if self.closed or self.studio.state['busy'] or (self.worker and self.worker.is_alive()):
                raise ValueError('Finish or cancel the current task first.')
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
            self.cancel_event = threading.Event()
            cancel = self.cancel_event
            self.files = {}
            self.value.update(status='running', progress=0, message='Preparing your recording…',
                              error=None, jobId=identity, sourceRevision=self.studio.source_revision,
                              sourceName=self.studio.name, stems=[])
            self.studio.state.update(busy=True, progress='Preparing stem separation…', error=None)

            def progress(fraction, message):
                with self.studio.lock:
                    if not cancel.is_set():
                        self.value.update(progress=max(0, min(1, float(fraction))), message=str(message))
                        self.studio.state['progress'] = str(message)

            def run():
                try:
                    if self.separator_factory:
                        separator = self.separator_factory(self.models, self.studio.ffmpeg)
                    else:
                        from .stems import Separator
                        separator = Separator(self.models, self.studio.ffmpeg)
                    outputs = separator.separate(source, pending, progress=progress, cancel_event=cancel)
                    if cancel.is_set():
                        return
                    if set(outputs) != set(STEMS):
                        raise ValueError('Stem separation did not produce all four tracks.')
                    for name in STEMS:
                        path = Path(outputs[name]).resolve()
                        if path.parent != pending.resolve() or not path.is_file() or path.stat().st_size <= 44:
                            raise ValueError('A separated track could not be saved.')
                    with self.studio.lock:
                        if cancel.is_set() or self.closed:
                            return
                        pending.rename(final)
                        self.files = {name: final / Path(outputs[name]).name for name in STEMS}
                        self.value.update(status='done', progress=1, message='Your four stems are ready.',
                                          stems=[{'id': name, 'label': name.title(),
                                                  'filename': name.title() + '.wav'} for name in STEMS])
                except Exception as error:
                    with self.studio.lock:
                        if not cancel.is_set():
                            self.value.update(status='failed', error=str(error) or 'Could not split this recording.',
                                              message='Stem separation could not finish.')
                finally:
                    shutil.rmtree(pending, ignore_errors=True)
                    with self.studio.lock:
                        if cancel.is_set() and self.value['status'] != 'done':
                            self.value.update(status='cancelled', message='Separation cancelled.', error=None, stems=[])
                        self.studio.state.update(busy=False, progress=self.value['message'])

            self.worker = threading.Thread(target=run, name='BlazeStemSeparation', daemon=True)
            self.worker.start()
            return self.snapshot()

    def cancel(self):
        with self.studio.lock:
            if self.value['status'] == 'running':
                self.cancel_event.set()
                self.value['message'] = 'Cancelling separation…'
        return self.snapshot()

    def file(self, identity, stem):
        with self.studio.lock:
            if (not isinstance(identity, str) or identity != self.value['jobId'] or
                    self.value['status'] != 'done' or stem not in STEMS or stem not in self.files):
                raise ValueError('Choose a completed stem from this separation.')
            source = self.files[stem]
            if not source.is_file():
                raise ValueError('The saved stem is missing.')
            return source

    def select(self, identity, stem):
        with self.studio.lock:
            if self.studio.state['busy']:
                raise ValueError('Finish or cancel the current task first.')
            source = self.file(identity, stem)
            if self.studio.imported and self.studio.source:
                self.studio.source.unlink(missing_ok=True)
            self.studio.source, self.studio.name, self.studio.imported = source, stem.title() + '.wav', False
            self.studio.source_revision += 1
            self.studio.state.update(name=self.studio.name, result=None, error=None,
                                     progress='Ready to analyse offline.', discoveryItem=None,
                                     sourceRevision=self.studio.source_revision, mediaKind='audio')

    def open_folder(self, identity):
        folder = self.file(identity, 'vocals').parent
        if sys.platform != 'darwin':
            raise ValueError('Open the Mac app to reveal the saved stems.')
        subprocess.Popen(['/usr/bin/open', str(folder)])

    def close(self):
        with self.studio.lock:
            self.closed = True
        self.cancel()
        if self.worker:
            self.worker.join(timeout=30)
