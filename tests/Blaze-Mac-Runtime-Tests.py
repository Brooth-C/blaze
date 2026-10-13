"""Desktop platform boundaries, isolated checks, and Cocoa launch cleanup."""
from pathlib import Path
from types import SimpleNamespace
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio import mac_app


class Tracker:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}

    def add_job(self, url, mode):
        return url


fake_blaze = SimpleNamespace(DownloadTracker=Tracker, Config=Mock(),
                             DownloadEngine=Mock(), validate_download_url=lambda url: url,
                             _shutdown_requested=False, _kill_all_active_processes=Mock())
with patch.dict(sys.modules, {'blaze': fake_blaze}):
    downloads = importlib.import_module('music_studio.downloads')


class DownloadsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.path_patch = patch.dict(os.environ)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.temporary.cleanup)
        self.app = downloads.Downloads(self.root / 'state', self.root / 'tools', self.root / 'media')

    def test_packaged_tools_follow_the_platform(self):
        for platform, ending in [('darwin', ''), ('linux', ''), ('win32', '.exe')]:
            with self.subTest(platform=platform), patch.object(downloads.sys, 'platform', platform):
                self.assertEqual(self.app.executable('yt-dlp'), self.root / 'tools' / ('yt-dlp' + ending))
                self.assertEqual(self.app.executable('node'), self.root / 'tools' / ('node' + ending))

    def test_macos_command_uses_bundled_node_and_downloader(self):
        self.app.tools.mkdir()
        for tool in ['yt-dlp', 'node']:
            (self.app.tools / tool).touch()
        body = {'urls': ['https://example.com/a'], 'mode': 'audio', 'format': 'wav', 'resolution': 'any'}
        with patch.object(downloads.sys, 'platform', 'darwin'), patch.object(downloads.threading, 'Thread'):
            self.app.start(body)
        command = fake_blaze.DownloadEngine.call_args.args[0]
        self.assertEqual(command, [str(self.app.tools / 'yt-dlp'), '--js-runtimes', 'node:' + str(self.app.tools / 'node')])

    def test_missing_bundled_downloader_never_uses_path(self):
        with patch.object(downloads.sys, 'platform', 'darwin'), self.assertRaisesRegex(ValueError, 'Downloader is missing'):
            self.app.start({'urls': ['https://example.com/a'], 'mode': 'audio', 'format': 'wav', 'resolution': 'any'})

    def test_macos_folder_open_is_an_argument_without_shell_expansion(self):
        with patch.object(downloads.sys, 'platform', 'darwin'), patch.object(downloads.subprocess, 'Popen') as launch:
            self.app.open_folder()
        self.assertEqual(launch.call_args.args[0], ['/usr/bin/open', str(self.app.output)])
        self.assertNotIn('shell', launch.call_args.kwargs)
        self.assertTrue(self.app.output.is_dir())

    def test_windows_folder_open_keeps_existing_behavior(self):
        with patch.object(downloads.sys, 'platform', 'win32'), patch.object(downloads.os, 'startfile', create=True) as launch:
            self.app.open_folder()
        launch.assert_called_once_with(self.app.output)

    def test_selected_download_cannot_escape_media_folder(self):
        self.app.output.mkdir()
        (self.root / 'outside.wav').touch()
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.app.select('../outside.wav')


class MacRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)

    def test_user_data_is_outside_the_app_bundle(self):
        with patch.object(mac_app.Path, 'home', return_value=self.root):
            self.assertEqual(mac_app.data_directory(), self.root / 'Library' / 'Application Support' / 'Blaze')
        self.assertEqual(mac_app.data_directory(self.root / 'custom'), (self.root / 'custom').resolve())

    def test_frozen_resources_are_read_from_the_bundle(self):
        with patch.object(mac_app.sys, '_MEIPASS', str(self.root), create=True):
            self.assertEqual(mac_app.resource_root(), self.root)

    def test_cocoa_main_thread_is_required_before_any_import_or_io(self):
        failures = []

        def worker():
            try:
                mac_app.launch(None, None, None, {})
            except RuntimeError as error:
                failures.append(str(error))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(failures, ['Blaze must start its Cocoa interface on the main thread.'])

    def fake_launch_dependencies(self):
        (self.root / 'bin').mkdir()
        (self.root / 'bin' / 'ffmpeg').touch()
        studio, server, window = Mock(), Mock(server_port=12345), Mock()
        webview = SimpleNamespace(settings={}, create_window=Mock(return_value=window), start=Mock())
        server_module = SimpleNamespace(Studio=Mock(return_value=studio), create_server=Mock(return_value=server))
        downloader_module = SimpleNamespace(Downloads=Mock())
        modules = {'webview': webview, 'music_studio.server': server_module, 'music_studio.downloads': downloader_module}
        return studio, server, window, webview, server_module, downloader_module, modules

    def test_native_window_and_model_paths_match_the_package(self):
        studio, server, _, webview, service, downloader, modules = self.fake_launch_dependencies()
        args = SimpleNamespace(file='song.wav', downloads_dir=self.root / 'downloads', ui_smoke=None)
        with patch.dict(sys.modules, modules), patch.object(mac_app.threading, 'Thread'):
            mac_app.launch(args, self.root, self.root / 'data', {})
        service.Studio.assert_called_once_with(self.root / 'data', str(self.root / 'bin' / 'ffmpeg'),
                                              'song.wav', self.root / 'music_studio' / 'models')
        downloader.Downloads.assert_called_once_with(self.root / 'data', self.root / 'bin', args.downloads_dir)
        self.assertEqual(webview.create_window.call_args.args, ('Blaze', 'http://127.0.0.1:12345/'))
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'cocoa')
        self.assertFalse(webview.start.call_args.kwargs['private_mode'])
        self.assertEqual(webview.start.call_args.kwargs['storage_path'], str(self.root / 'data' / 'webview'))
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        studio.close.assert_called_once()

    def test_failed_gui_still_stops_local_server_and_downloads(self):
        studio, server, _, webview, _, _, modules = self.fake_launch_dependencies()
        webview.start.side_effect = RuntimeError('Cocoa failed')
        args = SimpleNamespace(file=None, downloads_dir=None, ui_smoke=None)
        with patch.dict(sys.modules, modules), patch.object(mac_app.threading, 'Thread'), self.assertRaisesRegex(RuntimeError, 'Cocoa failed'):
            mac_app.launch(args, self.root, self.root / 'data', {})
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        studio.close.assert_called_once()

    def test_self_test_does_not_open_gui_or_user_data(self):
        with patch.object(mac_app, 'package_self_test') as check, patch.object(mac_app, 'launch') as launch:
            result = mac_app.main(['song.wav', '--self-test', str(self.root / 'report.json')])
        self.assertEqual(result, 0)
        check.assert_called_once()
        launch.assert_not_called()

    def test_ui_smoke_uses_isolated_state_and_downloads(self):
        def check(args, root, data, receipt):
            self.assertEqual(data, self.root / 'ui-smoke-data')
            self.assertEqual(args.downloads_dir, data / 'downloads')
            receipt['ok'] = True
        with patch.object(mac_app, 'launch', side_effect=check):
            result = mac_app.main(['song.wav', '--ui-smoke', str(self.root / 'report.json'), '--data-dir', str(self.root / 'unused')])
        self.assertEqual(result, 0)
        self.assertFalse((self.root / 'unused').exists())

    def test_automated_failure_reports_error_and_returns_nonzero(self):
        target = self.root / 'report.json'
        with patch.object(mac_app, 'launch', side_effect=RuntimeError('Native failure')), patch.object(mac_app, 'present_error') as alert:
            result = mac_app.main(['song.wav', '--ui-smoke', str(target)])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(target.read_text())['error'], 'Native failure')
        alert.assert_not_called()
        self.assertFalse(sys.stdout.closed)
        self.assertFalse(sys.stderr.closed)

    def test_ui_smoke_failure_always_writes_a_receipt_and_closes_window(self):
        target = self.root / 'report.json'
        receipt, window = {}, Mock()
        with patch.object(mac_app.traceback, 'print_exc'):
            mac_app.ui_smoke(window, None, target, receipt, mac_app.CocoaProbe(), timeout=0)
        self.assertFalse(json.loads(target.read_text())['ok'])
        self.assertIn('timed out', receipt['error'])
        window.destroy.assert_called_once()

    def test_smoke_probes_do_not_use_eval_or_relax_csp(self):
        probe = mac_app.CocoaProbe()
        window = Mock()
        view = Mock()
        native = view.evaluateJavaScript_completionHandler_
        native.side_effect = lambda script, callback: callback('{"ready":true}', None)
        helper = SimpleNamespace(AppHelper=SimpleNamespace(callAfter=lambda function, *args: function(*args)))
        cocoa = SimpleNamespace(BrowserView=SimpleNamespace(instances={window.uid: SimpleNamespace(webview=view)}))
        with patch.dict(sys.modules, {'PyObjCTools': helper, 'webview.platforms.cocoa': cocoa}):
            self.assertEqual(probe.probe(window, '({ready:true})'), {'ready': True})
        script = native.call_args.args[0]
        self.assertNotIn('eval(', script)
        self.assertIn('JSON.stringify', script)

    def test_probes_preserve_javascript_errors_as_test_failures(self):
        probe = mac_app.CocoaProbe()
        window = Mock()
        view = Mock()
        view.evaluateJavaScript_completionHandler_.side_effect = lambda script, callback: callback(None, 'Canvas failed')
        helper = SimpleNamespace(AppHelper=SimpleNamespace(callAfter=lambda function, *args: function(*args)))
        cocoa = SimpleNamespace(BrowserView=SimpleNamespace(instances={window.uid: SimpleNamespace(webview=view)}))
        with patch.dict(sys.modules, {'PyObjCTools': helper, 'webview.platforms.cocoa': cocoa}), self.assertRaisesRegex(RuntimeError, 'Canvas failed'):
            probe.probe(window, 'canvas()')

    def test_download_fixture_serves_only_one_local_file(self):
        source = self.root / 'original.wav'
        source.write_bytes(b'RIFF local test fixture')
        fixture = mac_app.SmokeFixture(source)
        self.addCleanup(fixture.close)
        with urlopen(fixture.url, timeout=2) as response:
            self.assertEqual(response.read(), source.read_bytes())
        with urlopen(Request(fixture.url, method='HEAD'), timeout=2) as response:
            self.assertEqual(int(response.headers['Content-Length']), source.stat().st_size)
            self.assertEqual(response.read(), b'')
        with self.assertRaises(HTTPError) as failure:
            urlopen(fixture.url.rsplit('/', 1)[0] + '/original.wav', timeout=2)
        self.assertEqual(failure.exception.code, 404)

    def test_missing_download_fixture_fails_before_starting_server(self):
        with self.assertRaisesRegex(ValueError, 'fixture is missing'):
            mac_app.SmokeFixture(self.root / 'missing.wav')


if __name__ == '__main__':
    unittest.main()
