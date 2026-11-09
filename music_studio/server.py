"""Blaze's desktop Studio UI, served only on loopback with packaged assets."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urlsplit, parse_qs, unquote, quote
import json
import hashlib
import mimetypes
import os
import re
import secrets
import shutil
from contextlib import suppress, nullcontext
from collections import OrderedDict
import threading
import uuid
import webbrowser
from .engine import ModelBundle, Analyzer, AnalysisCancelled, MAX_BYTES
from .store import Store, export_json, export_csv


def media_kind(source):
    return 'video' if source and Path(source).suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v') else 'audio'


def media_type(source):
    """Keep common recording types consistent across system MIME databases."""
    return {'.m4a': 'audio/mp4', '.mp4': 'video/mp4', '.m4v': 'video/mp4',
            '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.flac': 'audio/flac',
            '.aac': 'audio/aac', '.ogg': 'audio/ogg', '.opus': 'audio/ogg',
            '.webm': 'video/webm', '.mov': 'video/quicktime'}.get(Path(source).suffix.lower()) or mimetypes.guess_type(str(source))[0] or 'application/octet-stream'


class LoopbackHTTPServer(ThreadingHTTPServer):
    """Keep numeric loopback serving independent of local DNS discovery."""
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]


class Studio:
    def __init__(self, directory, ffmpeg, initial=None, models=None):
        self.directory = Path(directory)
        self.incoming = self.directory / 'incoming'
        self.incoming.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.directory)
        self.ffmpeg = ffmpeg
        self.model_directory = models
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.source = Path(initial).resolve() if initial else None
        self.imported = False
        self.name = self.source.name if self.source else ''
        self.state = {'busy': False, 'progress': 'Ready to analyse offline.' if self.source else 'Import an audio or video file to begin.', 'result': None, 'name': self.name}
        self.analyzer = None
        self.worker = None
        self.analysis_cancel = threading.Event()
        self.analysis_results = OrderedDict()
        self.result_identity = None
        self.analysis_aliases = {}
        self.closed = False
        self.downloader = None
        self.discovery = None
        self.stems = None
        self.waveforms = None
        self.practice_sessions = None
        self.presentation = 'desktop'
        self.source_revision = 0
        self.state.update(discoveryItem=None, sourceRevision=0, mediaKind=media_kind(self.source))
        self.appearance_path = self.directory / 'appearance.json'
        self.appearance = 'system'
        try:
            saved = json.loads(self.appearance_path.read_text(encoding='utf-8'))
            if isinstance(saved, dict) and saved.get('appearance') in ('system', 'light', 'dark'):
                self.appearance = saved['appearance']
        except (OSError, ValueError, TypeError):
            pass

    def open_local_file(self, selected):
        """Select a file returned by a native Open panel, never an HTTP path."""
        try:
            source = Path(selected).expanduser().resolve(strict=True)
            if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
                raise ValueError('Choose a media file smaller than 2 GB.')
            with source.open('rb') as stream:
                stream.read(1)
        except (OSError, TypeError):
            raise ValueError('The selected file could not be opened.') from None
        return self.select_source(source, source.name)

    def source_identity(self, source, stat=None):
        """Identify unchanged local bytes without reading a large file on the UI thread."""
        source = Path(source).resolve()
        stat = stat if stat is not None else source.stat()
        key = (str(source), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        return self.analysis_aliases.get(key, key)

    def remember_analysis(self, identity, result):
        self.analysis_results[identity] = result
        self.analysis_results.move_to_end(identity)
        while len(self.analysis_results) > 8:
            self.analysis_results.popitem(last=False)

    def associate_source_identity(self, identity, retained):
        """A completed separation owns a byte-for-byte retained original copy."""
        with self.lock:
            self.analysis_aliases[self.source_identity(retained)] = identity

    def select_source(self, source, name, imported=False, discovery_item=None):
        """Select trusted local media while an independently pinned Mac analysis runs."""
        with self.lock:
            if self.state['busy'] and self.presentation != 'mac':
                raise ValueError('Finish or cancel chord analysis first.')
            if self.result_identity is not None and self.state['result'] is not None:
                self.remember_analysis(self.result_identity, self.state['result'])
            source = Path(source).resolve()
            identity = self.source_identity(source)
            if self.imported and self.source and self.source != source:
                self.source.unlink(missing_ok=True)
            self.source, self.name, self.imported = source, name, imported
            self.source_revision += 1
            value = self.analysis_results.get(identity)
            self.result_identity = identity if value is not None else None
            self.state.update(name=name, result=value, error=None, discoveryItem=discovery_item,
                              sourceRevision=self.source_revision, mediaKind=media_kind(source))
            if not self.state['busy']:
                self.state['progress'] = 'Analysis saved on this device.' if value else 'Ready to analyse offline.'
            return {'name': name, 'sourceRevision': self.source_revision, 'mediaKind': media_kind(source)}

    def set_appearance(self, appearance):
        if appearance not in ('system', 'light', 'dark'):
            raise ValueError('Choose System, Light, or Dark appearance.')
        with self.lock:
            temporary = self.appearance_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'appearance': appearance}), encoding='utf-8')
            temporary.replace(self.appearance_path)
            self.appearance = appearance

    def analyze(self, selected):
        if selected not in ('major_minor', 'extended', 'refined', 'powerful'):
            raise ValueError('Choose an installed recognition model.')
        with self.lock:
            if self.closed:
                raise ValueError('Studio is closing.')
            if self.state['busy']:
                raise ValueError('An analysis is already running.')
            if self.source is None or not self.source.is_file():
                raise ValueError('Import an audio or video file first.')
            # Opening the file pins its bytes even if a browser import is later
            # unlinked. Copying and hashing happen on the worker, never in a UI handler.
            source, name = self.source, self.name
            stream = source.open('rb')
            input_stat = os.fstat(stream.fileno())
            source_key = self.source_identity(source, input_stat)
            pinned = (self.incoming / ('.analysis-' + uuid.uuid4().hex + source.suffix)
                      if self.presentation == 'mac' else None)
            cancel = threading.Event()
            self.analysis_cancel = cancel
            task = {'sourceName': name, 'sourceRevision': self.source_revision, 'status': 'running', 'error': None}
            self.state.update(busy=True, progress='Opening the local recognition model…', error=None, analysisTask=task)

            def check():
                if cancel.is_set():
                    raise AnalysisCancelled()

            def progress(message):
                with self.lock:
                    task['message'] = message
                    self.state['progress'] = 'Analysing ' + name + ': ' + message

            def run():
                result = None
                error = None
                cancelled = False
                try:
                    check()
                    digest = hashlib.sha256()
                    progress('Preparing recording…')
                    with stream, (pinned.open('xb') if pinned else nullcontext(None)) as copied:
                        total = 0
                        while block := stream.read(1024 * 1024):
                            check()
                            total += len(block)
                            if total > MAX_BYTES:
                                raise ValueError('Choose a media file smaller than 2 GB.')
                            if copied is not None:
                                if shutil.disk_usage(self.incoming).free < 128 * 1024 ** 2:
                                    raise ValueError('Free more storage before analysing this recording.')
                                copied.write(block)
                            digest.update(block)
                        final_stat = os.fstat(stream.fileno())
                        if pinned and (input_stat.st_size, input_stat.st_mtime_ns) != (final_stat.st_size, final_stat.st_mtime_ns):
                            raise ValueError('The recording changed while it was being read. Try analysis again.')
                    check()
                    bundle = ModelBundle(self.model_directory, selected)
                    check()
                    analyzer = Analyzer(bundle, self.ffmpeg)
                    with self.lock:
                        self.analyzer = analyzer
                    if cancel.is_set():
                        analyzer.cancel()
                    analyzer.check()
                    progress('Checking saved analysis…')
                    identity = self.store.identity({
                        'source_sha256': digest.hexdigest(),
                        'engine_version': 'structured1' if bundle.structured else 'overlap1',
                        'model': {'sha256': bundle.metadata['sha256'],
                                  'frontend_sha256': bundle.manifest['frontend']['sha256']}})
                    result = self.store.load(identity)
                    if result is None:
                        result = analyzer.analyze(pinned or source, progress)
                        check()
                        result = self.store.save(result)
                    check()
                    result['audio_file'] = name
                except AnalysisCancelled:
                    cancelled = True
                except Exception as failure:
                    error = str(failure) or 'Could not analyse this file.'
                finally:
                    with suppress(OSError):
                        stream.close()
                    if pinned:
                        with suppress(OSError):
                            pinned.unlink(missing_ok=True)
                    # Keep busy until cleanup is complete. A new job can never
                    # have its analyzer/progress cleared by an older worker.
                    with self.lock:
                        self.analyzer = None
                        self.state['busy'] = False
                        current_key = None
                        if self.source:
                            with suppress(OSError):
                                current_key = self.source_identity(self.source)
                        if cancelled:
                            task['status'] = 'cancelled'
                            self.state['progress'] = 'Chord analysis cancelled: ' + name
                        elif error:
                            task.update(status='failed', error=error)
                            self.state['progress'] = 'Chord analysis could not finish: ' + name
                            if current_key == source_key:
                                self.state['error'] = error
                        else:
                            task['status'] = 'done'
                            self.remember_analysis(source_key, result)
                            self.state['progress'] = 'Analysis ready: ' + name
                            if current_key == source_key:
                                self.result_identity = source_key
                                self.state.update(result=result, error=None)
                    if not cancelled and not error and self.practice_sessions is not None:
                        with suppress(OSError, ValueError):
                            self.practice_sessions.remember_analysis(source_key, result)
            self.worker = threading.Thread(target=run, name='BlazeMusicStudio', daemon=True)
            try:
                self.worker.start()
            except Exception:
                stream.close()
                self.worker = None
                self.state.update(busy=False, progress='Analysis could not start.')
                task.update(status='failed', error='The background worker could not start.')
                raise ValueError('The background worker could not start. Try again.') from None

    def cancel_analysis(self):
        with self.lock:
            self.analysis_cancel.set()
            if self.analyzer:
                self.analyzer.cancel()

    def close(self):
        with self.lock:
            self.closed = True
        self.cancel_analysis()
        if self.waveforms:
            self.waveforms.close()
        if self.stems:
            self.stems.close()
        if self.discovery:
            self.discovery.close()
        if self.downloader:
            self.downloader.close()
        if self.analyzer:
            self.analyzer.cancel()
        if self.worker:
            self.worker.join(timeout=10)
        if self.imported and self.source:
            self.source.unlink(missing_ok=True)


def create_server(studio, port=0):
    assets = Path(__file__).parent / 'web'
    def stems():
        if studio.presentation != 'mac':
            raise ValueError('Stem separation is available in the Mac app.')
        with studio.lock:
            if studio.stems is None:
                from .stem_jobs import StemJobs
                studio.stems = StemJobs(studio)
            return studio.stems

    def discovery():
        with studio.lock:
            if studio.discovery is None:
                from .discovery import Discovery
                tools = studio.downloader.tools if studio.downloader else Path(studio.ffmpeg).parent
                studio.discovery = Discovery(studio.directory, tools, studio.ffmpeg)
            return studio.discovery

    def practice_sessions():
        if studio.presentation != 'mac':
            raise ValueError('Practice is available in the Mac app.')
        stems()
        with studio.lock:
            if studio.practice_sessions is None:
                from .practice_sessions import PracticeSessions
                studio.practice_sessions = PracticeSessions(studio)
            return studio.practice_sessions

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

        def log_message(self, *_):
            pass

        def permitted(self, token=False):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected:
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected:
                return False
            if token:
                query = parse_qs(urlsplit(self.path).query)
                supplied = self.headers.get('X-Blaze-Token') or query.get('token', [''])[0]
                if not secrets.compare_digest(supplied, studio.token):
                    return False
            return True

        def send(self, data, status=200, content_type='application/json; charset=utf-8', extra=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def json(self, data, status=200):
            try:
                self.send(json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), status)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # A cancelled fetch has no recipient. Do not turn its failed
                # write into another JSON response on the disconnected socket.
                self.close_connection = True

        def do_GET(self):
            if not self.permitted():
                self.json({'error': 'Access denied.'}, 403)
                return
            path = urlsplit(self.path).path
            mac = studio.presentation == 'mac'
            names = {'/': 'index.html', '/studio.js': 'studio.js', '/flow.js': 'flow.js',
                     '/studio.css': 'studio.css', '/blaze-logo.png': 'blaze-logo.png'}
            if mac:
                names.update({'/mac-logic-preview.html': 'mac-logic-preview.html',
                              '/mac-logic-preview.css': 'mac-logic-preview.css', '/mac-logic-preview.js': 'mac-logic-preview.js',
                              '/mac-logic-live.js': 'mac-logic-live.js', '/mac-logic-live.css': 'mac-logic-live.css',
                              '/mac-practice.js': 'mac-practice.js', '/mac-practice.css': 'mac-practice.css',
                              '/mac.css': 'mac.css', '/mac.js': 'mac.js',
                              '/mac-stems.css': 'mac-stems.css', '/mac-stems.js': 'mac-stems.js',
                              '/mac-studio.css': 'mac-studio.css', '/mac-studio.js': 'mac-studio.js',
                              '/mac-harmony.css': 'mac-harmony.css', '/mac-harmony.js': 'mac-harmony.js',
                              '/studio-grand.png': 'studio-grand.png',
                              '/studio-instruments.png': 'studio-instruments.png'})
            if path in names:
                name = names[path]
                data = (assets / name).read_bytes()
                if path == '/':
                    data = data.replace(b'%%TOKEN%%', studio.token.encode())
                    data = data.replace(b'%%APPEARANCE%%', studio.appearance.encode())
                    data = data.replace(b'%%PRESENTATION%%', b'mac' if mac else b'desktop')
                    data = data.replace(b'%%MAC_STYLES%%', b'<link rel="stylesheet" href="/mac.css"><link rel="stylesheet" href="/mac-stems.css"><link rel="stylesheet" href="/mac-studio.css"><link rel="stylesheet" href="/mac-harmony.css">' if mac else b'')
                    if mac:
                        preview = (assets / 'mac-logic-preview.html').read_bytes()
                        template = preview.split(b'<main ', 1)[1].split(b'</main>', 1)[0]
                        live = (b'<template id="logic-live-template"><main ' + template + b'</main></template>'
                                b'<link rel="stylesheet" href="/mac-logic-preview.css">'
                                b'<link rel="stylesheet" href="/mac-logic-live.css">'
                                b'<link rel="stylesheet" href="/mac-practice.css">'
                                b'<script src="/mac.js"></script><script src="/mac-stems.js"></script>'
                                b'<script src="/mac-studio.js"></script><script src="/mac-harmony.js"></script>'
                                b'<script src="/mac-logic-live.js"></script><script src="/mac-logic-preview.js"></script>'
                                b'<script src="/mac-practice.js"></script>')
                    else:
                        live = b''
                    data = data.replace(b'%%MAC_SCRIPT%%', live)
                kind = ('text/html; charset=utf-8' if path == '/' or path.endswith('.html') else 'text/css; charset=utf-8'
                        if path.endswith('.css') else 'image/png' if path.endswith('.png')
                        else 'text/javascript; charset=utf-8')
                self.send(data, content_type=kind)
                return
            if not self.permitted(token=True):
                self.json({'error': 'Access denied.'}, 403)
                return
            if path == '/api/studio-waveform':
                if not mac:
                    self.json({'error': 'Not found.'}, 404)
                    return
                from .waveform import Waveforms, StaleWaveform, WaveformBusy, selection
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    if any(len(query.get(key, [])) > 1 for key in ('sourceRevision', 'jobId', 'stem')):
                        raise ValueError('Choose one recording and track.')
                    revision = query.get('sourceRevision', [''])[0]
                    job_id, stem = query.get('jobId', [''])[0], query.get('stem', [''])[0]
                    source, valid, _ = selection(studio, revision, job_id, stem)
                    with studio.lock:
                        if studio.waveforms is None:
                            studio.waveforms = Waveforms(studio.ffmpeg)
                        waveforms = studio.waveforms
                    value = waveforms.get(source, valid)
                    with studio.lock:
                        _, _, owned_job = selection(studio, revision, job_id, stem)
                        selected_stem = studio.stems.selected_stem() if owned_job else ''
                    self.json(dict(value, sourceRevision=int(revision), jobId=job_id, stem=stem,
                                   stemJobId=owned_job, selectedStem=selected_stem))
                except StaleWaveform as error:
                    self.json({'error': str(error)}, 409)
                except WaveformBusy as error:
                    self.json({'error': str(error)}, 503)
                except (ValueError, OSError, TypeError) as error:
                    self.json({'error': str(error) or 'The waveform is unavailable.'}, 400)
                return
            if path == '/api/practice':
                if not mac:
                    self.json({'error': 'Not found.'}, 404)
                    return
                try:
                    self.json(practice_sessions().snapshot())
                except (ValueError, OSError, TypeError) as error:
                    self.json({'error': str(error) or 'Saved practice could not be loaded.'}, 400)
                return
            if path in ('/api/stems', '/api/stem-file'):
                try:
                    manager = stems()
                    if path == '/api/stems':
                        self.json(manager.snapshot())
                    else:
                        query = parse_qs(urlsplit(self.path).query)
                        stem = query.get('stem', [''])[0]
                        job_id = query.get('jobId', [''])[0]
                        source = manager.file(job_id, stem)
                        descriptor = manager.descriptor(job_id, stem)
                        filename = descriptor.get('filename', stem.title() + '.wav')
                        with source.open('rb') as stream:
                            stream.seek(0, 2)
                            size = stream.tell()
                            stream.seek(0)
                            self.send_response(200)
                            self.send_header('Content-Type', media_type(source) if stem == 'source' else 'audio/wav')
                            self.send_header('Content-Length', str(size))
                            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(filename, safe=''))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('X-Content-Type-Options', 'nosniff')
                            self.end_headers()
                            try:
                                while block := stream.read(65536):
                                    self.wfile.write(block)
                            except OSError:
                                self.close_connection = True
                except (ValueError, OSError, TypeError) as error:
                    self.json({'error': str(error) or 'The stem is unavailable.'}, 400)
                return
            if path.startswith('/api/discovery'):
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    if path == '/api/discovery':
                        self.json(discovery().status(query.get('id', [''])[0]))
                    elif path == '/api/discovery-history':
                        self.json({'items': discovery().history()})
                    elif path == '/api/discovery-image':
                        data, content_type = discovery().image(query.get('id', [''])[0])
                        self.send(data, content_type=content_type)
                    else:
                        self.json({'error': 'Not found.'}, 404)
                except (ValueError, OSError, TypeError):
                    self.json({'error': 'This discovery request expired or is unavailable. Try again.'}, 400)
                return
            if path == '/api/state':
                with studio.lock:
                    self.json(studio.state)
                return
            if path == '/api/appearance':
                self.json({'appearance': studio.appearance})
                return
            if path == '/api/downloads':
                self.json(studio.downloader.state() if studio.downloader else {'unavailable': True})
                return
            if path == '/api/export':
                query = parse_qs(urlsplit(self.path).query)
                amount = int(query.get('transpose', ['0'])[0])
                if not -12 <= amount <= 12 or not studio.state['result']:
                    self.json({'error': 'No analysis to export.'}, 400)
                    return
                kind = query.get('format', ['json'])[0]
                if kind not in ('json', 'csv'):
                    self.json({'error': 'Choose JSON or CSV.'}, 400)
                    return
                data = export_json(studio.state['result'], amount) if kind == 'json' else export_csv(studio.state['result'], amount)
                self.send(data, content_type='application/json' if kind == 'json' else 'text/csv; charset=utf-8',
                          extra={'Content-Disposition': f'attachment; filename="Blaze-chords.{kind}"'})
                return
            if path == '/media':
                self.media()
                return
            self.json({'error': 'Not found.'}, 404)

        def media(self):
            revision = parse_qs(urlsplit(self.path).query).get('sourceRevision', [None])[0]
            with studio.lock:
                if revision is not None and revision != str(studio.source_revision):
                    self.json({'error': 'The selected recording changed.'}, 409)
                    return
                source = studio.source
            if source is None or not source.is_file():
                self.json({'error': 'No selected media.'}, 404)
                return
            size = source.stat().st_size
            begin, end = 0, size - 1
            header = self.headers.get('Range')
            if header:
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', header)
                if not match:
                    self.json({'error': 'Invalid media range.'}, 416)
                    return
                begin = int(match[1]); end = min(size - 1, int(match[2]) if match[2] else size - 1)
                if begin > end or begin >= size:
                    self.json({'error': 'Invalid media range.'}, 416)
                    return
            self.send_response(206 if header else 200)
            self.send_header('Content-Type', mimetypes.guess_type(str(source))[0] or 'application/octet-stream')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(end - begin + 1))
            self.send_header('Cache-Control', 'no-store')
            if header:
                self.send_header('Content-Range', f'bytes {begin}-{end}/{size}')
            self.end_headers()
            with source.open('rb') as stream:
                stream.seek(begin)
                remaining = end - begin + 1
                try:
                    while remaining:
                        block = stream.read(min(65536, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_POST(self):
            if not self.permitted(token=True):
                self.json({'error': 'Access denied.'}, 403)
                return
            path = urlsplit(self.path).path
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if path == '/api/import':
                    if not 0 < length <= MAX_BYTES or (studio.state['busy'] and studio.presentation != 'mac'):
                        raise ValueError('Finish or cancel analysis, then choose a file smaller than 2 GB.')
                    name = Path(unquote(self.headers.get('X-File-Name', 'Selected media')).replace('\\', '/')).name[:200]
                    suffix = Path(name).suffix[:16]
                    temporary = studio.incoming / (uuid.uuid4().hex + suffix)
                    try:
                        with temporary.open('wb') as out:
                            remaining = length
                            while remaining:
                                block = self.rfile.read(min(65536, remaining))
                                if not block:
                                    raise ValueError('The selected file was not fully read.')
                                out.write(block); remaining -= len(block)
                        studio.select_source(temporary, name, imported=True)
                    except Exception:
                        temporary.unlink(missing_ok=True)
                        raise
                    self.json({'name': name})
                    return
                if not 0 <= length <= 65536:
                    raise ValueError('The request is too large.')
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError('Choose a supported action.')
                if path in ('/api/practice-save', '/api/practice-open'):
                    if studio.presentation != 'mac':
                        self.json({'error': 'Not found.'}, 404)
                        return
                    manager = practice_sessions()
                    self.json(manager.save(body) if path == '/api/practice-save' else manager.open(body))
                    return
                if path.startswith('/api/stems-'):
                    manager = stems()
                    if path == '/api/stems-start':
                        self.json(manager.start(body.get('mode', 'stems')))
                    elif path == '/api/stems-cancel':
                        self.json(manager.cancel())
                    elif path == '/api/stems-select':
                        manager.select(body.get('jobId'), body.get('stem'), body.get('sourceRevision'))
                        self.json({'ok': True})
                    elif path == '/api/stems-folder':
                        manager.open_folder(body.get('jobId'))
                        self.json({'ok': True})
                    else:
                        self.json({'error': 'Not found.'}, 404)
                    return
                if path.startswith('/api/discovery'):
                    manager = discovery()
                    if path == '/api/discovery':
                        self.json(manager.request(body))
                    elif path == '/api/discovery-prepare':
                        self.json(manager.prepare(body))
                    elif path == '/api/discovery-select':
                        with studio.lock:
                            if studio.state['busy'] and studio.presentation != 'mac':
                                raise ValueError('Finish or cancel chord analysis first.')
                            source, item = manager.select(body.get('requestId'))
                            studio.select_source(source, item['title'], discovery_item=item)
                        self.json({'name': item['title'], 'item': item, 'mediaKind': media_kind(source)})
                    elif path == '/api/discovery-cancel':
                        manager.cancel(body.get('requestId'))
                        self.json({'ok': True})
                    elif path == '/api/discovery-listened':
                        manager.listened(body)
                        self.json({'ok': True})
                    elif path == '/api/discovery-reset':
                        manager.reset()
                        self.json({'ok': True})
                    else:
                        self.json({'error': 'Not found.'}, 404)
                    return
                if path == '/api/appearance':
                    studio.set_appearance(body.get('appearance'))
                    self.json({'appearance': studio.appearance})
                    return
                if path == '/api/fullscreen':
                    native = getattr(studio, 'native_fullscreen', None)
                    if native:
                        native()
                    self.json({'native': bool(native)})
                    return
                if path.startswith('/api/download-'):
                    if not studio.downloader:
                        raise ValueError('Open the complete Blaze app to use downloading.')
                    if path == '/api/download-start':
                        studio.downloader.start(body)
                    elif path == '/api/download-cancel':
                        studio.downloader.cancel()
                    elif path == '/api/download-folder':
                        studio.downloader.open_folder()
                    elif path == '/api/download-select':
                        with studio.lock:
                            if studio.state['busy'] and studio.presentation != 'mac':
                                raise ValueError('Finish or cancel chord analysis first.')
                            source = studio.downloader.select(body.get('id'))
                            studio.select_source(source, source.name)
                    else:
                        raise ValueError('Unknown download action.')
                elif path == '/api/analyze':
                    studio.analyze(body.get('model', 'powerful'))
                elif path == '/api/cancel':
                    studio.cancel_analysis()
                elif path == '/api/edit':
                    if studio.state['result'] is None:
                        raise ValueError('Analyse a recording first.')
                    studio.state['result'] = studio.store.edit(studio.state['result'], body.get('index'), body.get('chord', ''))
                elif path == '/api/rhythm':
                    if studio.state['result'] is None:
                        raise ValueError('Analyse a recording first.')
                    studio.state['result'] = studio.store.edit_rhythm(studio.state['result'], body.get('correction'))
                elif path == '/api/clear-cache':
                    studio.store.clear_cache()
                else:
                    self.json({'error': 'Not found.'}, 404)
                    return
                self.json({'ok': True})
            except (ValueError, OSError, TypeError) as error:
                self.close_connection = True
                self.json({'error': str(error) or 'Could not complete this action.'}, 400)
    server = LoopbackHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def launch(directory, ffmpeg, initial=None, models=None, open_browser=True):
    studio = Studio(directory, ffmpeg, initial, models)
    server = create_server(studio)
    address = f'http://127.0.0.1:{server.server_port}/'
    print('Blaze Music Studio · local interface:', address)
    print('All recognition runs on this device. Press Ctrl+C to close Studio.')
    if open_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        studio.close()
