"""Offline reliability and UI checks; run beside blaze.py."""
import importlib.util
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import zipfile
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('blaze_reliability', Path(__file__).with_name('blaze.py'))
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        b._shutdown_requested = False
        b.Logger.QUIET = True
        b.Logger._dashboard_tracker = None

    def tearDown(self):
        b._shutdown_requested = False

    def test_invalid_urls_rejected(self):
        for url in ('file:///etc/passwd', 'http://user:secret@example.org/a',
                    'http://example.org:70000/a', 'http://example.org/a b',
                    'https://open.spotify.com/track/example', 'https://example.org/\x1b'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                b.validate_download_url(url)

    def test_pasted_urls_preserve_query_and_deduplicate(self):
        urls = b.parse_url_input('"https://example.org/a?x=1&y=2" https://example.org/a?x=1&y=2\nhttps://example.org/b')
        self.assertEqual(urls, ['https://example.org/a?x=1&y=2', 'https://example.org/b'])

    def test_nan_progress_never_means_complete(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/a')
        for value in (float('nan'), float('inf'), '-inf', None, object()):
            tracker.update_job(jid, progress=value)
        self.assertEqual(tracker.jobs[jid].progress, 0)

    def test_terminal_job_clears_live_measurements(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/a')
        tracker.update_job(jid, status='downloading', speed='2 MiB/s', eta='00:04')
        tracker.update_job(jid, status='failed', error='disk full')
        self.assertEqual((tracker.jobs[jid].speed, tracker.jobs[jid].eta), ('', ''))

    def test_structured_progress_and_playlist_title(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/a')
        engine = object.__new__(b.DownloadEngine)
        engine._parse_ytdlp_line('BLAZE_MEDIA:' + json.dumps({'title': 'தமிழ் [song]', 'playlist_index': 2, 'playlist_count': 4}), jid, tracker)
        engine._parse_ytdlp_line('BLAZE_PROGRESS:' + json.dumps({'status': 'downloading', 'total_bytes': 1000, 'downloaded_bytes': 500, 'eta': 4, 'speed': 2048}), jid, tracker)
        job = tracker.jobs[jid]
        self.assertEqual((job.title, job.item_index, job.item_count), ('தமிழ் [song]', 2, 4))
        self.assertEqual((job.progress, job.speed, job.eta), (50, '2.0 KiB/s', '00:04'))
        engine._parse_ytdlp_line('BLAZE_PROGRESS:{"status":"finished"}', jid, tracker)
        self.assertEqual((job.progress, job.phase, job.speed, job.eta), (100, 'Finishing', '', ''))
        engine._parse_ytdlp_line('[ExtractAudio] Destination: shortened.mp3', jid, tracker)
        self.assertEqual(job.title, 'தமிழ் [song]')

    def test_corrupt_progress_does_not_crash(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/a')
        engine = object.__new__(b.DownloadEngine)
        for value in ('invalid', 'null', '[]', '{"status":"downloading","speed":"bad"}', '{"status":"downloading","total_bytes":NaN}'):
            engine._parse_ytdlp_line('BLAZE_PROGRESS:' + value, jid, tracker)
        self.assertEqual(tracker.jobs[jid].progress, 0)

    def test_new_playlist_item_resets_progress(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/a')
        tracker.update_job(jid, progress=100, speed='1 MiB/s', eta='00:01')
        object.__new__(b.DownloadEngine)._parse_ytdlp_line('BLAZE_MEDIA:{"title":"Second"}', jid, tracker)
        self.assertEqual((tracker.jobs[jid].progress, tracker.jobs[jid].speed, tracker.jobs[jid].eta), (0, '', ''))

    def test_all_view_order_stays_stable(self):
        tracker = b.DownloadTracker()
        for i in range(15):
            tracker.add_job(f'https://example.org/{i}')
        before = [job.id for job in b.dashboard_selected_jobs(list(tracker.jobs.values()), 'all')]
        tracker.update_job(1, status='done')
        tracker.update_job(2, status='failed')
        self.assertEqual(before, [job.id for job in b.dashboard_selected_jobs(list(tracker.jobs.values()), 'all')])
        self.assertEqual([job.id for job in b.dashboard_selected_jobs(list(tracker.jobs.values()), 'failed')], [2])
        self.assertNotIn(1, [job.id for job in b.dashboard_selected_jobs(list(tracker.jobs.values()), 'active')])

    def test_dashboard_bounds_across_terminal_sizes(self):
        from rich.console import Console
        from rich.cells import cell_len
        tracker = b.DownloadTracker()
        for i in range(25):
            jid = tracker.add_job(f'https://example.org/{i}')
            tracker.update_job(jid, title='Tamil தமிழ் 日本語 [literal]\n\x1b[31mtext', status='downloading', phase='Downloading', progress=50)
        tracker.update_job(1, status='failed', error='Disk full\n\x1b]0;bad title\x07')
        for width in (10, 20, 24, 30, 48, 65, 85, 100, 140):
            for height in (3, 8, 11, 12, 15, 20, 24, 40):
                for view in ('all', 'failed', 'active'):
                    with self.subTest(width=width, height=height, view=view):
                        stream = io.StringIO()
                        Console(file=stream, width=width, height=height, color_system=None).print(
                            b.build_terminal_dashboard(tracker, b.Config(), Path('/tmp'), 'auto', False, width, height, view=view))
                        lines = stream.getvalue().splitlines()
                        self.assertLessEqual(len(lines), height)
                        self.assertTrue(all(cell_len(line) <= width for line in lines))
                        self.assertNotIn('\x1b', stream.getvalue())

    def test_startup_banner_fits_narrow_windows(self):
        from rich.cells import cell_len
        for width in (1, 10, 18, 24, 30, 48, 50, 52, 56, 60, 80):
            for no_color in (False, True):
                with self.subTest(width=width, no_color=no_color):
                    with patch.object(b.Logger, 'QUIET', False), patch.object(b.Logger, 'NO_COLOR', no_color), patch.object(b.shutil, 'get_terminal_size', return_value=SimpleNamespace(columns=width)), patch('sys.stdout', new_callable=io.StringIO) as stream:
                        b.Logger.banner()
                    plain = b.re.sub(r'\x1b\[[0-9;]*m', '', stream.getvalue())
                    self.assertTrue(all(cell_len(line) <= width for line in plain.splitlines()))

    def test_logs_stay_inside_dashboard_and_restore(self):
        tracker = b.DownloadTracker()
        with patch.object(b.Logger, 'QUIET', False), patch('sys.stdout', new_callable=io.StringIO) as out, patch('sys.stderr', new_callable=io.StringIO) as err:
            with self.assertRaises(RuntimeError):
                with b.Logger.dashboard(tracker):
                    b.Logger.info('waiting')
                    b.Logger.error('disk full')
                    raise RuntimeError('test')
            self.assertEqual(out.getvalue() + err.getvalue(), '')
        self.assertIsNone(b.Logger._dashboard_tracker)
        self.assertIn('disk full', tracker.logs[-1])

    def test_no_urls_tui_rejects_malformed_input(self):
        engine = SimpleNamespace(tracker=None)
        with patch.object(b.DependencyInstaller, 'ensure_rich', return_value=True), patch.object(b, 'choose_download_mode', return_value='auto'), patch('rich.prompt.Prompt.ask', return_value='"unterminated'), patch('sys.stdout', new_callable=io.StringIO):
            self.assertFalse(b.run_tui([], Path('/tmp'), engine, b.Config()))
        self.assertIsNone(engine.tracker)

    def test_cancel_restores_tracker_and_logger(self):
        original = object()
        engine = SimpleNamespace(tracker=original, has_aria2c=False)
        def work(*args, **kwargs):
            while not b._shutdown_requested:
                time.sleep(0.01)
        engine.batch_parallel = work
        with patch.object(b.DependencyInstaller, 'ensure_rich', return_value=True), patch.object(b, 'dashboard_keys') as keys, patch('sys.stdout', new_callable=io.StringIO):
            keys.return_value.__enter__.return_value = lambda: 'q'
            with self.assertRaises(KeyboardInterrupt):
                b.run_tui(['https://example.org/a'], Path('/tmp'), engine, b.Config())
        self.assertIs(engine.tracker, original)
        self.assertIsNone(b.Logger._dashboard_tracker)
        self.assertTrue(b._shutdown_requested)

    def test_worker_exception_marks_failure(self):
        engine = SimpleNamespace(tracker=None, has_aria2c=False, batch_parallel=lambda *a, **k: (_ for _ in ()).throw(OSError('disk full')))
        with patch.object(b.DependencyInstaller, 'ensure_rich', return_value=True), patch('sys.stdout', new_callable=io.StringIO):
            self.assertFalse(b.run_tui(['https://example.org/a'], Path('/tmp'), engine, b.Config()))
        self.assertIsNone(engine.tracker)

    def test_invalid_config_values_are_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'config.json'
            path.write_text(json.dumps({'workers': 999999, 'fragments': 99999, 'tui_refresh_rate': 100000, 'retries': 9999, 'insecure': 'true'}))
            with patch.object(b, 'CONFIG_FILE', path):
                config = b.Config.load()
            self.assertEqual((config.workers, config.fragments, config.tui_refresh_rate, config.retries), (32, 64, 12, 100))
            self.assertFalse(config.insecure)

    def test_failed_config_save_cleans_temp(self):
        with tempfile.TemporaryDirectory() as root, patch.object(b, 'CONFIG_DIR', Path(root)), patch.object(b, 'CONFIG_FILE', Path(root) / 'config.json'), patch.object(Path, 'replace', side_effect=OSError('disk full')):
            b.Config().save()
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_aria_installs_by_default_but_respects_opt_out(self):
        with patch.object(b.DependencyInstaller, '_ensure_local_bin_in_path'), patch.object(b.DependencyInstaller, '_ensure_ytdlp', return_value=['yt-dlp']), patch.object(b.DependencyInstaller, '_ensure_ffmpeg'), patch.object(b.DependencyInstaller, '_ensure_aria2c', return_value=True) as aria, patch.object(b.DependencyInstaller, '_ensure_ffprobe') as probe:
            self.assertEqual(b.DependencyInstaller.ensure_all(), (['yt-dlp'], True))
            aria.assert_called_once_with()
            aria.reset_mock()
            self.assertEqual(b.DependencyInstaller.ensure_all(use_aria2c=False), (['yt-dlp'], False))
            aria.assert_not_called()
            probe.assert_not_called()

    def test_aria_checksum_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
            root = Path(folder)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            old = bin_dir / 'aria2c'
            old.write_bytes(b'existing executable')
            def download(url, destination):
                destination.write_bytes(b'tampered download')
                return True
            artifact = ('https://example.org/aria2c', '0' * 64, False)
            with patch.object(b, 'BLAZE_RUNTIME_DIR', root), patch.object(b, 'LOCAL_BIN_DIR', bin_dir), patch.object(b.sys, 'platform', 'darwin'), patch.object(b.platform, 'machine', return_value='arm64'), patch.dict(b.ARIA2_ARTIFACTS, {('darwin', 'arm64'): artifact}), patch.object(b.DependencyInstaller, '_aria2_binary_works', return_value=False) as verify, patch.object(b.DependencyInstaller, '_download_file', side_effect=download):
                self.assertFalse(b.DependencyInstaller._ensure_aria2c(private_only=True))
                verify.assert_called_once_with(old)
            self.assertEqual(old.read_bytes(), b'existing executable')
            self.assertEqual(list(root.iterdir()), [bin_dir])

    def test_aria_unrunnable_candidate_preserves_existing_binary(self):
        body = b'verified but incompatible executable'
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
            root = Path(folder)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            old = bin_dir / 'aria2c'
            old.write_bytes(b'old executable')
            def download(url, destination):
                destination.write_bytes(body)
                return True
            artifact = ('https://example.org/aria2c', hashlib.sha256(body).hexdigest(), False)
            with patch.object(b, 'BLAZE_RUNTIME_DIR', root), patch.object(b, 'LOCAL_BIN_DIR', bin_dir), patch.object(b.sys, 'platform', 'darwin'), patch.object(b.platform, 'machine', return_value='arm64'), patch.dict(b.ARIA2_ARTIFACTS, {('darwin', 'arm64'): artifact}), patch.object(b.DependencyInstaller, '_aria2_binary_works', return_value=False), patch.object(b.DependencyInstaller, '_download_file', side_effect=download):
                self.assertFalse(b.DependencyInstaller._ensure_aria2c(private_only=True))
            self.assertEqual(old.read_bytes(), b'old executable')
            self.assertEqual(list(root.iterdir()), [bin_dir])

    def test_aria_verified_mac_and_windows_publish_privately(self):
        for platform, target, is_zip in (('darwin', 'aria2c', False), ('win32', 'aria2c.exe', True)):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as folder, patch.dict(os.environ):
                root = Path(folder)
                bin_dir = root / 'bin'
                body = b'portable executable'
                if is_zip:
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, 'w') as archive:
                        archive.writestr('aria2/' + target, body)
                        archive.writestr('../escape.txt', b'never extracted')
                    payload = buffer.getvalue()
                else:
                    payload = body
                def download(url, destination):
                    destination.write_bytes(payload)
                    return True
                artifact = ('https://example.org/aria2c', hashlib.sha256(payload).hexdigest(), is_zip)
                with patch.object(b, 'BLAZE_RUNTIME_DIR', root), patch.object(b, 'LOCAL_BIN_DIR', bin_dir), patch.object(b.sys, 'platform', platform), patch.object(b.platform, 'machine', return_value='AMD64'), patch.dict(b.ARIA2_ARTIFACTS, {(platform, 'x64'): artifact}), patch.object(b.DependencyInstaller, '_aria2_binary_works', return_value=True), patch.object(b.DependencyInstaller, '_download_file', side_effect=download) as fetch:
                    self.assertTrue(b.DependencyInstaller._ensure_aria2c(private_only=True))
                    self.assertEqual((bin_dir / target).read_bytes(), body)
                    self.assertEqual(list(root.iterdir()), [bin_dir])
                    self.assertTrue(b.DependencyInstaller._ensure_aria2c(private_only=True))
                    fetch.assert_called_once()

    def test_aria_requires_expected_version_and_https(self):
        for code, output, expected in ((0, 'aria2 version 1.37.0\nEnabled Features: HTTPS', True),
                                       (0, 'aria2 version 1.37.0', False),
                                       (0, 'aria2 version 1.36.0\nHTTPS', False),
                                       (1, 'aria2 version 1.37.0\nHTTPS', False)):
            with self.subTest(output=output, code=code), patch.object(b.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout=output)):
                self.assertEqual(b.DependencyInstaller._aria2_binary_works(Path('aria2c')), expected)

    def test_error_diagnostic_fails_even_on_zero_exit(self):
        with tempfile.TemporaryDirectory() as root:
            engine = b.DownloadEngine([sys.executable], b.Config(), False)
            engine._report_path = Path(root) / 'report.json'
            result = engine._run_command([sys.executable, '-c', 'print("ERROR: unavailable")'])
            self.assertNotEqual(result, 0)
            self.assertEqual(engine._last_error, 'ERROR: unavailable')
            self.assertEqual(b._active_processes, set())

    def test_media_title_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            engine = b.DownloadEngine([sys.executable], b.Config(), False)
            engine._report_path = Path(root) / 'report.json'
            result = engine._run_command([sys.executable, '-c', 'print("[download] Destination: ERROR song.mp4")'])
            self.assertEqual(result, 0)

    def test_reader_start_failure_reaps_child(self):
        with tempfile.TemporaryDirectory() as root:
            engine = b.DownloadEngine([sys.executable], b.Config(), False)
            engine._report_path = Path(root) / 'report.json'
            with patch.object(threading.Thread, 'start', side_effect=RuntimeError('thread unavailable')):
                with self.assertRaises(RuntimeError):
                    engine._run_command([sys.executable, '-c', 'import time; time.sleep(5)'])
            self.assertEqual(b._active_processes, set())

    def test_silent_child_is_cancellable(self):
        with tempfile.TemporaryDirectory() as root:
            engine = b.DownloadEngine([sys.executable], b.Config(), False)
            engine._report_path = Path(root) / 'report.json'
            timer = threading.Timer(0.2, lambda: setattr(b, '_shutdown_requested', True))
            timer.start()
            start = time.monotonic()
            try:
                self.assertEqual(engine._run_command([sys.executable, '-c', 'import time; time.sleep(10)']), 130)
            finally:
                timer.cancel()
            self.assertLess(time.monotonic() - start, 4)
            self.assertEqual(b._active_processes, set())


if __name__ == '__main__':
    unittest.main()
