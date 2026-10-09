"""Run beside Blaze-Universal-4.1.20.py: python3 Blaze-Regression-Tests.py"""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
if sys.platform != "win32":
    import tty  # Load real termios aliases before terminal mocks.
spec = importlib.util.spec_from_file_location('blaze_under_test', Path(__file__).with_name('blaze.py'))
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)
b.Logger.QUIET = True

class InstallerTests(unittest.TestCase):
    def run_install(self, failure=None, code=0):
        def download(url, dest):
            dest.write_bytes(b'new binary')
            return True
        with tempfile.TemporaryDirectory() as root, patch.object(b, 'LOCAL_BIN_DIR', Path(root)):
            target = 'yt-dlp.exe' if b.sys.platform == 'win32' else ('yt-dlp_macos' if 'arm' in b.platform.machine().lower() else 'yt-dlp_macos_legacy') if b.sys.platform == 'darwin' else 'yt-dlp'
            dest = Path(root) / target
            dest.write_bytes(b'old binary')
            with patch.object(b.DependencyInstaller, '_download_file', side_effect=download), patch.object(b.subprocess, 'run', side_effect=failure, return_value=SimpleNamespace(returncode=code)):
                try:
                    result = b.DependencyInstaller._download_ytdlp_standalone()
                except KeyboardInterrupt:
                    self.assertEqual(list(Path(root).iterdir()), [dest])
                    self.assertEqual(dest.read_bytes(), b'old binary')
                    raise
            self.assertEqual(list(Path(root).iterdir()), [dest])
            return result, dest.read_bytes()

    def test_verified_binary_replaces_old(self):
        result, data = self.run_install()
        self.assertIsNotNone(result)
        self.assertEqual(data, b'new binary')

    def test_invalid_binary_keeps_old(self):
        result, data = self.run_install(code=1)
        self.assertIsNone(result)
        self.assertEqual(data, b'old binary')

    def test_execution_failure_cleans_temp(self):
        result, data = self.run_install(failure=OSError('cannot execute'))
        self.assertIsNone(result)
        self.assertEqual(data, b'old binary')

    @unittest.skipIf(sys.platform == 'win32', 'Windows does not chmod executable files')
    def test_chmod_failure_cleans_temp(self):
        with patch.object(b.os, 'chmod', side_effect=PermissionError('chmod denied')):
            result, data = self.run_install()
        self.assertIsNone(result)
        self.assertEqual(data, b'old binary')

    def test_interruption_cleans_temp(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_install(failure=KeyboardInterrupt())

class EditorTests(unittest.TestCase):
    def test_quoted_windows_path(self):
        with patch.object(b.sys, 'platform', 'win32'), patch.object(b.subprocess, 'call', return_value=0) as call:
            self.assertEqual(b.open_config_editor('"C:\\Program Files\\Editor\\editor.exe" --wait'), 0)
            self.assertEqual(call.call_args.args[0][0], 'C:\\Program Files\\Editor\\editor.exe')

    def test_invalid_editor(self):
        with patch.object(b.subprocess, 'call') as call:
            self.assertEqual(b.open_config_editor(''), 1)
            self.assertEqual(b.open_config_editor('"unterminated'), 1)
            call.assert_not_called()

    def test_editor_failed_exit(self):
        with patch.object(b.subprocess, 'call', return_value=3):
            self.assertEqual(b.open_config_editor('editor'), 1)

class DashboardTests(unittest.TestCase):
    def setUp(self):
        b._shutdown_requested = False

    def test_responsive_rendering(self):
        import io
        from rich.console import Console
        from rich.cells import cell_len
        tracker = b.DownloadTracker()
        for i in range(30):
            jid = tracker.add_job(f"https://example.org/{i}")
            tracker.update_job(jid, title="Tamil தமிழ் title [literal] " + str(i),
                               status="downloading", progress=50, speed="2 MiB/s")
        tracker.update_job(1, status="failed", error="Permission denied [literal]")
        for width, height in ((30, 15), (40, 20), (48, 24), (65, 24), (100, 30)):
            with self.subTest(width=width, height=height):
                stream = io.StringIO()
                console = Console(file=stream, width=width, height=height, color_system=None)
                console.print(b.build_terminal_dashboard(tracker, b.Config(), Path('/tmp'),
                                                        'auto', False, width, height))
                lines = stream.getvalue().splitlines()
                self.assertLessEqual(len(lines), height)
                self.assertTrue(all(cell_len(line) <= width for line in lines))
                self.assertIn('more', stream.getvalue())
                if height >= 20:
                    self.assertIn('Permission denied', stream.getvalue())

    def test_multiline_titles_do_not_expand_rows(self):
        import io
        from rich.console import Console
        tracker = b.DownloadTracker()
        tracker.update_job(tracker.add_job('https://example.org/video'), title='A\nB\nC')
        stream = io.StringIO()
        Console(file=stream, width=60, height=24).print(b.build_terminal_dashboard(
            tracker, b.Config(), Path('/tmp'), 'auto', False, 60, 24))
        self.assertIn('A B C', stream.getvalue())

    def test_dashboard_start_failure_restores_tracker(self):
        engine = SimpleNamespace(tracker=object(), has_aria2c=False, batch_parallel=unittest.mock.Mock())
        original = engine.tracker
        with patch.object(b.DependencyInstaller, 'ensure_rich', return_value=True), patch('rich.live.Live.__enter__', side_effect=RuntimeError('display failed')):
            with self.assertRaises(RuntimeError):
                b.run_tui(['https://example.org/video'], Path('/tmp'), engine, b.Config())
        engine.batch_parallel.assert_not_called()
        self.assertIs(engine.tracker, original)

    def test_interactive_dashboard(self):
        engine = SimpleNamespace(download=unittest.mock.Mock(return_value=True))
        with patch.object(b.DependencyInstaller, 'ensure_rich', return_value=False), patch.object(b, 'run_tui', return_value=True) as dashboard, patch('builtins.input', return_value='https://example.org/video'), patch.object(b, 'ask_yes_no', return_value=False), patch.object(b, 'newest_video_after', return_value=None):
            self.assertEqual(b.interactive_download_loop(engine, b.Config(), Path('/tmp'), True,
                                                       'video', False, False, False), 0)
        dashboard.assert_called_once()
        engine.download.assert_not_called()

    def test_no_tui_interactive_fallback(self):
        engine = SimpleNamespace(download=unittest.mock.Mock(return_value=True))
        with patch.object(b, 'run_tui') as dashboard, patch('builtins.input', return_value='https://example.org/video'), patch.object(b, 'ask_yes_no', return_value=False), patch.object(b, 'newest_video_after', return_value=None):
            self.assertEqual(b.interactive_download_loop(engine, b.Config(), Path('/tmp'), True,
                                                       'video', False, False, False, use_tui=False), 0)
        dashboard.assert_not_called()
        engine.download.assert_called_once()


class DashboardStageTests(unittest.TestCase):
    def test_download_eta_then_conversion(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/audio')
        engine = object.__new__(b.DownloadEngine)
        engine._parse_ytdlp_line('[download]  75.0% of 10MiB at 2.0MiB/s ETA 00:04', jid, tracker)
        self.assertEqual(tracker.jobs[jid].eta, '00:04')
        self.assertEqual(tracker.jobs[jid].phase, 'Downloading')
        engine._parse_ytdlp_line('[ExtractAudio] Destination: song.mp3', jid, tracker)
        self.assertEqual(tracker.jobs[jid].phase, 'Converting')
        self.assertEqual(tracker.jobs[jid].eta, '')
        self.assertEqual(tracker.jobs[jid].speed, '')

    def test_merging_and_metadata_stages(self):
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/video')
        engine = object.__new__(b.DownloadEngine)
        engine._parse_ytdlp_line('[Merger] Merging formats', jid, tracker)
        self.assertEqual(tracker.jobs[jid].phase, 'Merging')
        engine._parse_ytdlp_line('[Metadata] Adding metadata', jid, tracker)
        self.assertEqual(tracker.jobs[jid].phase, 'Finishing')

    def test_session_summary_and_eta_render(self):
        import io
        from rich.console import Console
        tracker = b.DownloadTracker()
        jid = tracker.add_job('https://example.org/song')
        tracker.update_job(jid, status='downloading', phase='Downloading', eta='00:04')
        stream = io.StringIO()
        Console(file=stream, width=120).print(b.build_terminal_dashboard(
            tracker, b.Config(), Path('/tmp'), 'audio', False, 120, 30, 65))
        text = stream.getvalue()
        for value in ('00:01:05', 'Jobs finished 0/1', '00:04', 'Downloading'):
            self.assertIn(value, text)


class DashboardNavigationTests(unittest.TestCase):
    def render(self, tracker, **kwargs):
        import io
        from rich.console import Console
        stream = io.StringIO()
        Console(file=stream, width=100).print(b.build_terminal_dashboard(
            tracker, b.Config(), Path('/tmp'), 'auto', False, 100, 24, **kwargs))
        return stream.getvalue()

    def test_pages_expose_hidden_jobs(self):
        tracker = b.DownloadTracker()
        for i in range(15):
            tracker.update_job(tracker.add_job(f'https://example.org/{i}'), title=f'unique-job-{i:02}')
        first = self.render(tracker, page=0)
        second = self.render(tracker, page=1)
        self.assertIn('unique-job-00', first)
        self.assertNotIn('unique-job-00', second)
        self.assertIn('unique-job-07', second)
        self.assertIn('Page 2/3', second)
        self.assertIn('Page 3/3', self.render(tracker, page=-1))

    def test_failure_filter(self):
        tracker = b.DownloadTracker()
        tracker.update_job(tracker.add_job('https://example.org/good'), title='success-title', status='done')
        tracker.update_job(tracker.add_job('https://example.org/bad'), title='failed-title', status='failed')
        text = self.render(tracker, view='failed')
        self.assertIn('failed-title', text)
        self.assertNotIn('success-title', text)

    def test_empty_failure_filter(self):
        self.assertIn('No failed downloads', self.render(b.DownloadTracker(), view='failed'))

    def test_noninteractive_keys_do_not_touch_terminal(self):
        with patch.object(b.sys.stdin, 'isatty', return_value=False):
            with b.dashboard_keys() as poll:
                self.assertEqual(poll(), '')

    @unittest.skipIf(sys.platform == 'win32', 'POSIX terminal restoration')
    def test_terminal_restored_on_exception(self):
        import termios
        with patch.object(b.sys.stdin, 'isatty', return_value=True), patch.object(b.sys.stdout, 'isatty', return_value=True), patch.object(b.sys.stdin, 'fileno', return_value=9), patch('termios.tcgetattr', return_value=['saved']), patch('tty.setcbreak'), patch('termios.tcsetattr') as restore:
            with self.assertRaises(RuntimeError):
                with b.dashboard_keys():
                    raise RuntimeError('render failed')
            restore.assert_called_once_with(9, termios.TCSADRAIN, ['saved'])


class NativeTerminalTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == 'win32', 'POSIX pseudoterminal test')
    def test_real_key_input_and_terminal_restoration(self):
        import os
        import pty
        import select
        import termios
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        try:
            with patch.object(b.sys, 'stdin', SimpleNamespace(isatty=lambda: True, fileno=lambda: slave)), patch.object(b.sys, 'stdout', SimpleNamespace(isatty=lambda: True)):
                with b.dashboard_keys() as poll:
                    os.write(master, b'n')
                    self.assertTrue(select.select([slave], [], [], 1)[0])
                    self.assertEqual(poll(), 'n')
                    self.assertEqual(poll(), '')
            self.assertEqual(termios.tcgetattr(slave), original)
        finally:
            os.close(master)
            os.close(slave)


class PrivateInstallationTests(unittest.TestCase):
    def test_all_owned_paths_inside_blaze(self):
        for path in (b.CONFIG_DIR, b.LOCAL_BIN_DIR, b.BLAZE_VENV_DIR, b.BLAZE_STATE_DIR):
            self.assertTrue(path.is_relative_to(b.DEFAULT_OUTPUT))

    def test_pip_uses_only_private_environment(self):
        with patch.object(b.DependencyInstaller, '_is_frozen', return_value=False), patch.object(b.DependencyInstaller, '_pip_install_in_private_venv', return_value=True) as private, patch.object(b.subprocess, 'run') as run:
            self.assertTrue(b.DependencyInstaller._pip_install('rich'))
            private.assert_called_once_with('rich', timeout=180)
            run.assert_not_called()

    def test_private_pip_command_and_temp_paths(self):
        with tempfile.TemporaryDirectory() as root, patch.object(b, 'BLAZE_RUNTIME_DIR', Path(root)), patch.object(b, 'BLAZE_VENV_DIR', Path(root) / 'venv'), patch.object(b.DependencyInstaller, '_add_venv_to_environment'), patch.object(b.subprocess, 'run') as run:
            self.assertTrue(b.DependencyInstaller._pip_install_in_private_venv('rich'))
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertIn('--require-virtualenv', commands[1])
            self.assertIn('--no-cache-dir', commands[1])
            self.assertNotIn('--user', commands[1])
            self.assertTrue(Path(commands[1][0]).is_relative_to(Path(root)))
            for call in run.call_args_list:
                env = call.kwargs['env']
                self.assertEqual(env['TMPDIR'], str(Path(root) / 'tmp'))
                self.assertEqual(env['PIP_CONFIG_FILE'], b.os.devnull)

    def test_package_manager_installers_disabled(self):
        with patch.object(b.subprocess, 'run') as run:
            self.assertFalse(b.DependencyInstaller._install_via_package_manager('ffmpeg'))
            self.assertFalse(b.DependencyInstaller._install_via_package_manager_visible('mpv'))
            run.assert_not_called()

    def test_update_does_not_modify_external_ytdlp(self):
        with patch.object(b.shutil, 'which', return_value='/usr/bin/yt-dlp'), patch.object(b.DependencyInstaller, '_pip_install', return_value=True) as install, patch.object(b.subprocess, 'run') as run:
            self.assertTrue(b.UpdateChecker.check_ytdlp(['yt-dlp']))
            install.assert_called_once_with('yt-dlp')
            run.assert_not_called()


class PrivateInstallIntegrationTests(unittest.TestCase):
    def test_real_offline_install_stays_in_private_venv(self):
        import zipfile
        import subprocess
        with tempfile.TemporaryDirectory() as root, patch.object(b, 'BLAZE_RUNTIME_DIR', Path(root)), patch.object(b, 'BLAZE_VENV_DIR', Path(root) / 'venv'), patch.object(b.DependencyInstaller, '_add_venv_to_environment'):
            wheel = Path(root) / 'blaze_isolation_probe-1.0-py3-none-any.whl'
            info = 'blaze_isolation_probe-1.0.dist-info/'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr('blaze_isolation_probe.py', 'VALUE = 123\n')
                archive.writestr(info + 'METADATA', 'Metadata-Version: 2.1\nName: blaze-isolation-probe\nVersion: 1.0\n')
                archive.writestr(info + 'WHEEL', 'Wheel-Version: 1.0\nGenerator: Blaze test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
                archive.writestr(info + 'RECORD', '')
            self.assertTrue(b.DependencyInstaller._pip_install_in_private_venv(str(wheel)))
            result = subprocess.run([str(b.DependencyInstaller._venv_python()), '-c', 'import sys, blaze_isolation_probe; print(sys.prefix); print(blaze_isolation_probe.__file__)'], check=True, capture_output=True, text=True)
            for location in result.stdout.splitlines():
                self.assertTrue(Path(location).is_relative_to(Path(root) / 'venv'))


if __name__ == '__main__':
    unittest.main()
