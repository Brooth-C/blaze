"""Real offline downloads, conversions, history and resume. Requires yt-dlp and FFmpeg."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location('blaze_integration', Path(__file__).with_name('blaze.py'))
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)


class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yt_dlp  # noqa: F401 -- fail clearly when test dependencies are missing.
        cls.ffmpeg = shutil.which('ffmpeg')
        if not cls.ffmpeg:
            raise RuntimeError('Put FFmpeg on PATH before running integration tests.')
        cls.fixture_root = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_root.name)
        def generate(args, filename):
            subprocess.run([cls.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y'] + args + [str(root / filename)], check=True, timeout=30)
        generate(['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1'], 'song.wav')
        generate(['-f', 'lavfi', '-i', 'sine=frequency=660:sample_rate=44100', '-t', '30'], 'slow.wav')
        generate(['-f', 'lavfi', '-i', 'testsrc=size=160x90:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '1', '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p', '-c:a', 'aac'], 'clip.mp4')
        cls.ranges = []
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)
            def log_message(self, *args):
                pass
            def do_GET(self):
                if urlsplit(self.path).path != '/slow.wav':
                    return super().do_GET()
                data = (root / 'slow.wav').read_bytes()
                offset = int(self.headers.get('Range', 'bytes=0-').split('=')[-1].split('-')[0])
                cls.ranges.append(offset)
                self.send_response(206 if offset else 200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(len(data) - offset))
                if offset:
                    self.send_header('Content-Range', f'bytes {offset}-{len(data)-1}/{len(data)}')
                self.end_headers()
                try:
                    for i in range(offset, len(data), 16384):
                        self.wfile.write(data[i:i + 16384])
                        self.wfile.flush()
                        time.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)
        cls.fixture_root.cleanup()

    def setUp(self):
        b._shutdown_requested = False
        b.Logger.QUIET = True
        self.destination = tempfile.TemporaryDirectory()
        self.root = Path(self.destination.name)
        self.config = b.Config(output_dir=str(self.root), format='mp3', workers=2,
                               write_metadata=False, write_thumbnails=False, use_aria2c=False, retries=0)
        self.tracker = b.DownloadTracker()
        self.engine = b.DownloadEngine([sys.executable, '-m', 'yt_dlp'], self.config, False, self.tracker)

    def tearDown(self):
        b._shutdown_requested = True
        b._kill_all_active_processes()
        self.destination.cleanup()
        b._shutdown_requested = False

    def download(self, name, mode='audio'):
        url = self.base_url + '/' + name
        jid = self.tracker.add_job(url)
        result = self.engine.download(url, self.root, mode=mode, job_id=jid)
        return result, self.tracker.jobs[jid]

    def reports(self):
        return [json.loads(path.read_text(encoding='utf-8')) for path in (self.root / 'Reports').glob('*.json')]

    def test_audio_conversion_and_progress(self):
        success, job = self.download('song.wav')
        self.assertTrue(success, job.error)
        files = list((self.root / 'Audio').glob('*.mp3'))
        self.assertEqual(len(files), 1)
        check = subprocess.run([self.ffmpeg, '-hide_banner', '-i', str(files[0]), '-f', 'null', '-'], capture_output=True, text=True, timeout=15)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn('Audio: mp3', check.stderr)
        self.assertEqual((job.status, job.progress), ('done', 100))
        log = next((self.root / 'Reports').glob('*.log')).read_text(encoding='utf-8')
        self.assertIn('BLAZE_MEDIA:', log)
        self.assertIn('BLAZE_PROGRESS:', log)
        self.assertEqual(self.reports()[0]['status'], 'succeeded')

    def test_history_skips_existing_and_retries_deleted_file(self):
        self.assertTrue(self.download('song.wav')[0])
        file = next((self.root / 'Audio').glob('*.mp3'))
        modified = file.stat().st_mtime_ns
        self.assertTrue(self.download('song.wav')[0])
        self.assertEqual(file.stat().st_mtime_ns, modified)
        file.unlink()
        self.assertTrue(self.download('song.wav')[0])
        self.assertTrue(file.is_file())
        self.config.format = 'flac'
        self.assertTrue(self.download('song.wav')[0])
        self.assertTrue(next((self.root / 'Audio').glob('*.flac')).is_file())

    def test_mixed_batch_keeps_audio_and_video(self):
        urls = [self.base_url + '/song.wav', self.base_url + '/clip.mp4']
        self.assertEqual(self.engine.batch_parallel(urls, self.root, 2), (2, 0))
        video = next((self.root / 'Video').glob('*.mp4'))
        check = subprocess.run([self.ffmpeg, '-hide_banner', '-i', str(video), '-f', 'null', '-'], capture_output=True, text=True, timeout=15)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn('Video:', check.stderr)
        self.assertIn('Audio:', check.stderr)
        self.assertTrue(next((self.root / 'Audio').glob('*.mp3')).is_file())
        self.assertEqual(b._active_processes, set())

    def test_http_error_is_failed_and_reported(self):
        success, job = self.download('missing.wav')
        self.assertFalse(success)
        self.assertEqual(job.status, 'failed')
        self.assertIn('404', job.error)
        self.assertEqual(self.reports()[0]['status'], 'failed')
        self.assertEqual(b._active_processes, set())

    def test_partial_download_resumes_after_cancel(self):
        self.config.format = 'wav'
        self.ranges.clear()
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(self.download('slow.wav')), daemon=True)
        thread.start()
        deadline = time.monotonic() + 15
        partial = None
        while time.monotonic() < deadline and thread.is_alive():
            partial = next((self.root / 'Audio').glob('*.part'), None)
            if partial and partial.stat().st_size > 65536:
                break
            time.sleep(0.02)
        try:
            self.assertIsNotNone(partial, 'Downloader did not create a partial file')
            b._shutdown_requested = True
            thread.join(timeout=6)
            self.assertFalse(thread.is_alive(), 'Cancellation left the worker running')
            self.assertFalse(outcome[0][0])
            self.assertTrue(partial.is_file())
            self.assertIn('interrupted', [report['status'] for report in self.reports()])
            self.assertEqual(b._active_processes, set())
            b._shutdown_requested = False
            success, job = self.download('slow.wav')
            self.assertTrue(success, job.error)
            self.assertTrue(any(offset > 0 for offset in self.ranges), 'Resume did not request remaining bytes')
            self.assertFalse(partial.exists())
            self.assertEqual(next((self.root / 'Audio').glob('*.wav')).stat().st_size,
                             (Path(self.fixture_root.name) / 'slow.wav').stat().st_size)
        finally:
            b._shutdown_requested = True
            b._kill_all_active_processes()
            thread.join(timeout=6)


if __name__ == '__main__':
    unittest.main()
