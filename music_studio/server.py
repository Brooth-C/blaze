"""Blaze's desktop Studio UI, served only on loopback with packaged assets."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urlsplit, parse_qs, unquote
import json
import hashlib
import mimetypes
import re
import secrets
import threading
import uuid
import webbrowser
from .engine import ModelBundle, Analyzer, AnalysisCancelled, MAX_BYTES
from .store import Store, export_json, export_csv


def media_kind(source):
    return 'video' if source and Path(source).suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v') else 'audio'


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
        self.downloader = None
        self.discovery = None
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
            if self.state['busy']:
                raise ValueError('An analysis is already running.')
            if self.source is None or not self.source.is_file():
                raise ValueError('Import an audio or video file first.')
            self.state.update(busy=True, progress='Opening the local recognition model…', error=None)
            source, name = self.source, self.name

        def run():
            try:
                bundle = ModelBundle(self.model_directory, selected)
                analyzer = Analyzer(bundle, self.ffmpeg)
                with self.lock:
                    self.analyzer = analyzer
                def progress(message):
                    with self.lock:
                        self.state['progress'] = message
                progress('Checking saved analysis…')
                digest = hashlib.sha256()
                if source.stat().st_size > MAX_BYTES:
                    raise ValueError('Choose a media file smaller than 2 GB.')
                with source.open('rb') as stream:
                    while block := stream.read(65536):
                        analyzer.check()
                        digest.update(block)
                identity = self.store.identity({
                    'source_sha256': digest.hexdigest(),
                    'engine_version': 'structured1' if bundle.structured else 'overlap1',
                    'model': {'sha256': bundle.metadata['sha256'],
                              'frontend_sha256': bundle.manifest['frontend']['sha256']}})
                result = self.store.load(identity)
                if result is None:
                    result = analyzer.analyze(source, progress)
                    result = self.store.save(result)
                result['audio_file'] = name
                with self.lock:
                    self.state.update(result=result, progress='Analysis saved on this device.', busy=False, error=None)
            except AnalysisCancelled:
                with self.lock:
                    self.state.update(busy=False, progress='Analysis cancelled. Your file is kept.')
            except Exception as error:
                with self.lock:
                    self.state.update(busy=False, error=str(error) or 'Could not analyse this file.', progress='Analysis could not finish.')
            finally:
                with self.lock:
                    self.analyzer = None
        self.worker = threading.Thread(target=run, name='BlazeMusicStudio', daemon=True)
        self.worker.start()

    def close(self):
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
    def discovery():
        with studio.lock:
            if studio.discovery is None:
                from .discovery import Discovery
                tools = studio.downloader.tools if studio.downloader else Path(studio.ffmpeg).parent
                studio.discovery = Discovery(studio.directory, tools, studio.ffmpeg)
            return studio.discovery

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
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
            self.send(json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), status)

        def do_GET(self):
            if not self.permitted():
                self.json({'error': 'Access denied.'}, 403)
                return
            path = urlsplit(self.path).path
            if path in ('/', '/studio.js', '/flow.js', '/studio.css', '/blaze-logo.png'):
                name = {'/': 'index.html', '/studio.js': 'studio.js', '/flow.js': 'flow.js', '/studio.css': 'studio.css', '/blaze-logo.png': 'blaze-logo.png'}[path]
                data = (assets / name).read_bytes()
                if path == '/':
                    data = data.replace(b'%%TOKEN%%', studio.token.encode())
                    data = data.replace(b'%%APPEARANCE%%', studio.appearance.encode())
                self.send(data, content_type={'/': 'text/html; charset=utf-8', '/studio.js': 'text/javascript; charset=utf-8', '/flow.js': 'text/javascript; charset=utf-8', '/studio.css': 'text/css; charset=utf-8', '/blaze-logo.png': 'image/png'}[path])
                return
            if not self.permitted(token=True):
                self.json({'error': 'Access denied.'}, 403)
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
                    if not 0 < length <= MAX_BYTES or studio.state['busy']:
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
                        with studio.lock:
                            if studio.imported and studio.source:
                                studio.source.unlink(missing_ok=True)
                            studio.source, studio.name, studio.imported = temporary, name, True
                            studio.source_revision += 1
                            studio.state.update(name=name, result=None, error=None, progress='Ready to analyse offline.',
                                                discoveryItem=None, sourceRevision=studio.source_revision,
                                                mediaKind=media_kind(temporary))
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
                if path.startswith('/api/discovery'):
                    manager = discovery()
                    if path == '/api/discovery':
                        self.json(manager.request(body))
                    elif path == '/api/discovery-prepare':
                        self.json(manager.prepare(body))
                    elif path == '/api/discovery-select':
                        with studio.lock:
                            if studio.state['busy']:
                                raise ValueError('Finish or cancel chord analysis first.')
                            source, item = manager.select(body.get('requestId'))
                            if studio.imported and studio.source:
                                studio.source.unlink(missing_ok=True)
                            studio.source, studio.name, studio.imported = source, item['title'], False
                            studio.source_revision += 1
                            studio.state.update(name=item['title'], result=None, error=None,
                                                progress='Ready to analyse offline.', discoveryItem=item,
                                                sourceRevision=studio.source_revision, mediaKind=media_kind(source))
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
                            if studio.state['busy']:
                                raise ValueError('Finish or cancel chord analysis first.')
                            source = studio.downloader.select(body.get('id'))
                            studio.source, studio.name, studio.imported = source, source.name, False
                            studio.source_revision += 1
                            studio.state.update(name=source.name, result=None, error=None, progress='Ready to analyse offline.',
                                                discoveryItem=None, sourceRevision=studio.source_revision,
                                                mediaKind=media_kind(source))
                    else:
                        raise ValueError('Unknown download action.')
                elif path == '/api/analyze':
                    studio.analyze(body.get('model', 'powerful'))
                elif path == '/api/cancel':
                    if studio.analyzer:
                        studio.analyzer.cancel()
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
