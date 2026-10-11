"""Embedded downloader with bounded playlists and cancellable native processing."""
import contextvars
import json
from pathlib import Path
import subprocess
import threading
from urllib.parse import urlsplit
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import ffmpeg as ffmpeg_module


class DownloadCancelled(Exception):
    pass


_session = contextvars.ContextVar('blaze_session', default=None)
_sessions = {}
_lock = threading.Lock()
_original_popen = ffmpeg_module.Popen


class Session:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = threading.Event()
        self.processes = set()

    def check(self):
        if self.cancelled.is_set() or self.callback.isCancelled():
            raise DownloadCancelled('Stopped. Retry to resume supported partial downloads.')


class CancellablePopen(_original_popen):
    def __init__(self, *args, **kwargs):
        self.blaze_session = _session.get()
        if self.blaze_session:
            self.blaze_session.check()
        super().__init__(*args, **kwargs)
        if self.blaze_session:
            with _lock:
                self.blaze_session.processes.add(self)
                stopped = self.blaze_session.cancelled.is_set()
            if stopped:
                self.kill()

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            if self.blaze_session:
                with _lock:
                    self.blaze_session.processes.discard(self)


ffmpeg_module.Popen = CancellablePopen


def cancel(token):
    with _lock:
        session = _sessions.get(token)
        if not session:
            return
        session.cancelled.set()
        processes = list(session.processes)
    for process in processes:
        try:
            process.terminate()
        except ProcessLookupError:
            continue

        def reap(proc=process):
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        threading.Thread(target=reap, daemon=True).start()


def validate_url(url):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 32 for c in url):
        raise ValueError('Paste a complete HTTPS link.')
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Paste a complete HTTPS link without login credentials.')
    _ = parsed.port
    return parsed._replace(scheme='https').geturl()


def settings(options_json):
    values = json.loads(options_json)
    if not isinstance(values, dict):
        raise ValueError('Invalid download settings.')
    quality = str(values.get('quality', 'best'))
    audio = values.get('audio', 'original')
    playlist = values.get('playlist', False)
    if quality not in ('best', '2160', '1440', '1080', '720', '480', '360'):
        raise ValueError('Choose a supported video quality.')
    if audio not in ('original', 'mp3', 'm4a', 'wav', 'flac') or not isinstance(playlist, bool):
        raise ValueError('Choose a supported audio format.')
    return quality, audio, playlist


class MobileYDL(YoutubeDL):
    def urlopen(self, request):
        session = _session.get()
        if session:
            session.check()
        response = super().urlopen(request)
        if session:
            try:
                session.check()
            except DownloadCancelled:
                response.close()
                raise
        return response


class QuietLogger:
    def debug(self, message):
        session = _session.get()
        if session:
            session.check()
    warning = debug
    error = debug


def download(url, mode, directory, callback, options_json='{}', ffmpeg_path='', quickjs_path='', token='local'):
    url = validate_url(url)
    if mode not in ('video', 'audio'):
        raise ValueError('Choose video or audio.')
    quality, audio, playlist = settings(options_json)
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    session = Session(callback)
    with _lock:
        if token in _sessions:
            raise ValueError('This download is already running.')
        _sessions[token] = session
    context = _session.set(session)

    def progress(data):
        session.check()
        total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
        done = data.get('downloaded_bytes') or 0
        percent = min(100, done * 100 / total) if total else -1
        callback.onProgress(float(percent), 'Finishing stream…' if data['status'] == 'finished' else 'Downloading…')

    def processing(data):
        session.check()
        callback.onProgress(-1.0, 'Converting / merging…')

    try:
        session.check()
        native = bool(ffmpeg_path and Path(ffmpeg_path).is_file())
        if mode == 'audio' and audio != 'original' and not native:
            raise ValueError('Media tools unavailable. Reinstall the complete Blaze APK.')
        audio_selector = ('bestaudio/best[vcodec=none]/best[ext=mp3]/best[ext=m4a]/best[ext=aac]/'
                          'best[ext=ogg]/best[ext=opus]/best[ext=wav]/best[ext=flac]')
        if mode == 'audio' and audio != 'original':
            audio_selector += '/best'  # Extraction from combined video is supported by FFmpeg.
        limit = '' if quality == 'best' else f'[height<=?{quality}]'
        video_selector = f'bestvideo{limit}+bestaudio/best{limit}' if native else 'best[vcodec!=none][acodec!=none]/best'
        options = {
            'format': audio_selector if mode == 'audio' else video_selector,
            'outtmpl': str(folder / 'source.%(ext)s'),
            'noplaylist': not playlist, 'extract_flat': 'in_playlist' if playlist else False,
            'playlistend': 201, 'restrictfilenames': True, 'continuedl': True,
            'socket_timeout': 10, 'retries': 2, 'fragment_retries': 2,
            'progress_hooks': [progress], 'postprocessor_hooks': [processing],
            'quiet': True, 'no_warnings': True, 'noprogress': True,
            'ignoreconfig': True, 'cachedir': False, 'logger': QuietLogger(),
            'postprocessors': [], 'fixup': 'detect_or_warn' if native else 'never',
            'merge_output_format': 'mkv',
        }
        if native:
            options['ffmpeg_location'] = ffmpeg_path
        if quickjs_path and Path(quickjs_path).is_file():
            options['js_runtimes'] = {'quickjs': {'path': quickjs_path}}
        if mode == 'audio' and audio != 'original':
            options['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': audio, 'preferredquality': '192'}]
        with MobileYDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
            session.check()
            if not info:
                raise ValueError('The website returned no media.')
            if info.get('_type') in ('playlist', 'multi_video'):
                if not playlist:
                    raise ValueError('Enable playlist mode to queue this playlist.')
                entries = []
                seen = set()
                for entry in info.get('entries') or []:
                    session.check()
                    if len(entries) >= 200:
                        raise ValueError('Playlists are limited to 200 items. Use a smaller playlist.')
                    if not entry:
                        continue
                    candidate = entry.get('webpage_url') or entry.get('url')
                    if candidate:
                        try:
                            candidate = validate_url(candidate)
                        except ValueError:
                            continue
                        if candidate not in seen:
                            seen.add(candidate)
                            entries.append({'url': candidate, 'title': str(entry.get('title') or 'Playlist item')[:200]})
                if not entries:
                    raise ValueError('No available HTTPS items in this playlist.')
                return json.dumps({'playlist_entries': entries, 'title': str(info.get('title') or 'Playlist')[:200]})
            if mode == 'video' and (info.get('vcodec') == 'none' or info.get('acodec') == 'none') and not info.get('requested_formats'):
                raise ValueError('No video with sound available. Try audio mode.')
            if mode == 'audio' and audio == 'original' and info.get('vcodec') not in (None, 'none'):
                raise ValueError('No audio-only stream available. Choose MP3 to extract audio.')
            if info.get('is_live'):
                raise ValueError('Live streams are not supported by this queue.')
            downloader.process_info(info)
            session.check()
            filename = Path(info.get('filepath') or downloader.prepare_filename(info)).resolve()
            if filename.parent != folder or not filename.is_file() or filename.stat().st_size == 0:
                raise ValueError('No complete output file was produced.')
            return json.dumps({'path': str(filename), 'title': str(info.get('title') or filename.name)[:200],
                               'bytes': filename.stat().st_size, 'height': info.get('height') or 0})
    except Exception:
        session.check()
        raise
    finally:
        _session.reset(context)
        with _lock:
            _sessions.pop(token, None)
