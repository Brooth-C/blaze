"""Desktop adapter around Blaze's existing download engine."""
from pathlib import Path
from dataclasses import asdict
import os
import threading
import blaze


class Downloads:
    def __init__(self, directory, tools, output=None):
        self.tools = Path(tools)
        self.output = Path(output or Path.home() / 'Downloads' / 'Blaze').resolve()
        self.directory = Path(directory)
        blaze.BLAZE_STATE_DIR = self.directory / 'download-state'
        blaze.LOCAL_BIN_DIR = self.tools
        os.environ['PATH'] = str(self.tools) + os.pathsep + os.environ.get('PATH', '')
        self.tracker = blaze.DownloadTracker()
        self.lock = threading.RLock()
        self.worker = None

    def state(self):
        with self.tracker.lock:
            jobs = [asdict(j) for j in self.tracker.jobs.values()]
        return {'busy': bool(self.worker and self.worker.is_alive()), 'jobs': jobs,
                'output': str(self.output), 'files': self.files()}

    def files(self):
        allowed = {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.opus', '.aac', '.mp4', '.mkv', '.webm', '.mov'}
        if not self.output.is_dir():
            return []
        files = [p for p in self.output.rglob('*') if p.is_file() and p.suffix.lower() in allowed
                 and p.resolve().is_relative_to(self.output)]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [{'id': p.relative_to(self.output).as_posix(), 'name': p.name} for p in files[:200]]

    def select(self, identity):
        if not isinstance(identity, str):
            raise ValueError('Choose a downloaded file.')
        p = (self.output / identity).resolve()
        if not p.is_relative_to(self.output) or not p.is_file() or identity not in {f['id'] for f in self.files()}:
            raise ValueError('The downloaded media is missing.')
        return p

    def start(self, body):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise ValueError('Finish or cancel the current downloads first.')
            urls = body.get('urls', [])
            if not isinstance(urls, list) or not 1 <= len(urls) <= 50 or not all(isinstance(u, str) and len(u) <= 8192 for u in urls):
                raise ValueError('Enter between 1 and 50 URLs, one per line.')
            urls = list(dict.fromkeys(blaze.validate_download_url(u) for u in urls))
            mode, fmt, resolution = body.get('mode'), body.get('format'), body.get('resolution')
            if mode not in ('audio', 'video') or fmt not in ('wav', 'mp3', 'flac', 'm4a', 'ogg', 'opus') or resolution not in ('any', '1080p', '4k', '8k'):
                raise ValueError('Choose a supported format and resolution.')
            if not (self.tools / 'yt-dlp.exe').is_file():
                raise ValueError('Downloader is missing. Extract the complete Blaze ZIP.')
            self.output.mkdir(parents=True, exist_ok=True)
            config = blaze.Config(format=fmt, mode=mode, video_resolution=resolution,
                                  use_aria2c=False, write_thumbnails=False)
            cmd = [str(self.tools / 'yt-dlp.exe')]
            if (self.tools / 'node.exe').is_file():
                cmd += ['--js-runtimes', 'node:' + str(self.tools / 'node.exe')]
            engine = blaze.DownloadEngine(cmd, config, False, self.tracker)
            blaze._shutdown_requested = False
            ids = [self.tracker.add_job(u, mode) for u in urls]
            def run():
                for u, identity in zip(urls, ids):
                    if blaze._shutdown_requested:
                        self.tracker.update_job(identity, status='failed', error='Cancelled; partial files are kept.')
                        continue
                    engine.download(u, self.output, mode, bool(body.get('playlist')), identity)
            self.worker = threading.Thread(target=run, name='BlazeDownloads', daemon=True)
            self.worker.start()

    def cancel(self):
        blaze._shutdown_requested = True
        blaze._kill_all_active_processes()

    def close(self):
        if self.worker and self.worker.is_alive():
            self.cancel()
            self.worker.join(timeout=10)
