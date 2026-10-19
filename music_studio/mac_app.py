"""Blaze's offline macOS desktop app, using the system Cocoa web view."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler
import argparse
import json
import mimetypes
import subprocess
import sys
import threading
import time
import traceback
import uuid


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def data_directory(override=None):
    return Path(override).resolve() if override else Path.home() / 'Library' / 'Application Support' / 'Blaze'


def present_error(message):
    """Present startup failures without needing a working web view."""
    try:
        from AppKit import NSAlert, NSAlertStyleCritical
        alert = NSAlert.alloc().init()
        alert.setAlertStyle_(NSAlertStyleCritical)
        alert.setMessageText_('Blaze could not open')
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_('OK')
        alert.runModal()
    except Exception:
        subprocess.run(['/usr/bin/osascript', '-e',
                        'display alert "Blaze could not open" message ' + json.dumps(message) + ' as critical'],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def package_self_test(source, destination, root):
    from music_studio.engine import ModelBundle, Analyzer
    from music_studio.store import Store, export_json, export_csv
    if not source:
        raise ValueError('Provide a local media file for the package self-test.')
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    result = Analyzer(ModelBundle(root / 'music_studio' / 'models', 'powerful'),
                      str(root / 'bin' / 'ffmpeg')).analyze(source)
    store = Store(target.parent / 'self-test-data')
    result = store.save(result)
    result = store.edit(result, 0, 'C:maj')
    target.write_bytes(export_json(result))
    target.with_suffix('.csv').write_bytes(export_csv(result))


class CocoaProbe:
    """Use WKWebView's native evaluator without eval or a page bridge."""
    def run(self, window, script):
        from PyObjCTools import AppHelper
        from webview.platforms.cocoa import BrowserView
        ready, report = threading.Event(), {}

        def completed(value, error):
            report.update(value=value, error=error)
            ready.set()

        def evaluate():
            try:
                native_view = BrowserView.instances[window.uid].webview
                native_view.evaluateJavaScript_completionHandler_(script, completed)
            except Exception as error:
                completed(None, error)

        AppHelper.callAfter(evaluate)
        if not ready.wait(timeout=2):
            raise RuntimeError('The native UI did not answer a test probe.')
        if report['error']:
            raise RuntimeError(str(report['error']))
        return report['value']

    def probe(self, window, expression):
        value = self.run(window, 'JSON.stringify((' + expression + '))')
        return json.loads(value) if value is not None else None


class SmokeFixture:
    """Serve one local test file, never its containing directory."""
    def __init__(self, source):
        self.source = Path(source).resolve()
        if not self.source.is_file():
            raise ValueError('The local download fixture is missing.')
        name = 'blaze-ui-' + uuid.uuid4().hex + self.source.suffix
        route = '/' + name
        source = self.source

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def respond(self, body):
                if self.path != route:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(source.stat().st_size))
                self.end_headers()
                if body:
                    try:
                        with source.open('rb') as stream:
                            while block := stream.read(65536):
                                self.wfile.write(block)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def do_HEAD(self):
                self.respond(False)

            def do_GET(self):
                self.respond(True)

        from music_studio.server import LoopbackHTTPServer
        self.server = LoopbackHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.server.server_port}' + route
        threading.Thread(target=self.server.serve_forever, name='BlazeSmokeFixture', daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def capture_screenshot(destination):
    if sys.platform == 'darwin':
        subprocess.run(['/usr/sbin/screencapture', '-x', str(destination)], check=True, timeout=15)
    else:
        from PIL import ImageGrab
        ImageGrab.grab().save(destination)


def ui_smoke(window, studio, destination, receipt, probe, timeout=240):
    """Exercise the packaged Cocoa UI and engine; the report preserves failures."""
    target = Path(destination).resolve()
    deadline = time.monotonic() + timeout
    fixture = None

    def wait_for(script, condition=lambda value: bool(value)):
        last_error = None
        while time.monotonic() < deadline:
            try:
                value = probe.probe(window, script)
                if condition(value):
                    return value
            except Exception as error:
                last_error = error
            if studio is not None:
                with studio.lock:
                    error = studio.state.get('error')
                if error:
                    raise RuntimeError(error)
                for job in studio.downloader.state()['jobs']:
                    if job['status'] == 'failed':
                        raise RuntimeError(job.get('error') or 'The native download queue failed.')
            time.sleep(.1)
        raise RuntimeError('The packaged Cocoa UI check timed out.' + (f' {last_error}' if last_error else ''))

    try:
        wait_for("document.readyState === 'complete' && typeof BlazeFlow !== 'undefined' && !!document.getElementById('import')")
        receipt['controls'] = probe.probe(window, """(() => {
          const ids = ['tab-downloads','tab-studio','tab-library','import','analyze',
            'play','previous','next','loop','speed','instrument','volume','down','up',
            'edit','export-json','export-csv','studio-settings','download-start','download-folder'];
          return ids.filter(id => !document.getElementById(id));
        })()""")
        if receipt['controls']:
            raise RuntimeError('The packaged app is missing controls: ' + ', '.join(receipt['controls']))
        wait_for("!!sourceName")
        probe.run(window, "document.getElementById('tab-downloads').click()")
        wait_for("!document.getElementById('downloads-panel').hidden && !document.getElementById('download-start').disabled")
        fixture = SmokeFixture(studio.source)
        probe.run(window, "document.getElementById('download-urls').value=" + json.dumps(fixture.url) +
                  "; document.getElementById('download-mode').value='audio'; "
                  "document.getElementById('download-format').value='wav'; document.getElementById('download-start').click()")
        wait_for("[...document.querySelectorAll('#download-jobs small')].some(node => node.textContent === 'Complete')")
        state = studio.downloader.state()
        completed = [job for job in state['jobs'] if job['url'] == fixture.url and job['status'] == 'done']
        files = [file for file in state['files'] if 'blaze-ui-' in file['name'] and file['name'].lower().endswith('.wav')]
        if len(completed) != 1 or not files:
            raise RuntimeError('The native download UI did not finish its local WAV fixture.')
        downloaded = files[0]
        downloaded_path = studio.downloader.select(downloaded['id'])
        if not downloaded_path.stat().st_size:
            raise RuntimeError('The native download produced an empty file.')
        receipt['download'] = {'status': completed[0]['status'], 'file': downloaded['name'],
                               'size': downloaded_path.stat().st_size, 'format': 'wav'}
        file_name = json.dumps(downloaded['name'])
        probe.run(window, "document.getElementById('tab-library').click()")
        wait_for("[...document.querySelectorAll('#download-files .download-row')].some(row => row.querySelector('span')?.textContent === " + file_name + ")")
        probe.run(window, "[...document.querySelectorAll('#download-files .download-row')].find(row => row.querySelector('span')?.textContent === " + file_name + ").querySelector('button').click()")
        wait_for("document.getElementById('downloads-panel').hidden && document.getElementById('filename').textContent === " + file_name + " && document.getElementById('media').readyState >= 1")
        with studio.lock:
            if studio.source != downloaded_path:
                raise RuntimeError('Open in Studio did not select the downloaded WAV file.')
        fixture.close()
        fixture = None
        probe.run(window, "document.getElementById('analyze').click()")
        wait_for("!!result && !busy")
        with studio.lock:
            result = studio.state['result']
            error = studio.state.get('error')
        if error or not result or not result.get('chords'):
            raise RuntimeError(error or 'The native app did not produce a chord analysis.')
        receipt['model'] = result['model']
        receipt['chords'] = len(result['chords'])
        receipt['engine_version'] = result['engine_version']
        if receipt['engine_version'] != 'structured1':
            raise RuntimeError('The native app did not use the advanced chord ensemble.')
        receipt['diagram_count'] = probe.probe(window, "document.querySelectorAll('.diagram-card canvas').length")
        if receipt['diagram_count'] != 3:
            raise RuntimeError('The app did not draw the current and upcoming chord keyboards.')
        receipt['layout'] = probe.probe(window, """(() => {
          const viewport = document.documentElement;
          const ids = ['bar-flow','diagram-strip','analyze','studio-settings'];
          return {width: innerWidth, height: innerHeight,
            scroll_height: viewport.scrollHeight,
            keyboards_visible: Array.from(document.querySelectorAll('.diagram-card canvas')).every(canvas => {const r=canvas.getBoundingClientRect();return r.height>=65 && r.top>=0 && r.bottom<=innerHeight;}),
            branding_fits: document.querySelector('header .brand h1').getBoundingClientRect().right <= document.querySelector('header').getBoundingClientRect().right,
            controls_visible: ids.every(id => {
              const r = document.getElementById(id).getBoundingClientRect();
              return r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= innerHeight + 1;
            })};
        })()""")
        if (not receipt['layout']['controls_visible'] or not receipt['layout']['branding_fits'] or not receipt['layout']['keyboards_visible']
                or receipt['layout']['scroll_height'] > receipt['layout']['height'] + 1):
            raise RuntimeError('The native app layout hides controls or requires vertical scrolling.')
        # Invoke the same handler as the play button. The native media clock,
        # rather than a mocked player response, confirms decoding and movement.
        probe.run(window, "document.getElementById('media').currentTime = 0; document.getElementById('play').click()")
        started = wait_for("(() => {const m = document.getElementById('media'); return !m.paused && m.currentTime > .2 ? m.currentTime : null;})()")
        advanced = wait_for("document.getElementById('media').currentTime", lambda value: value > started + .25)
        receipt['playback'] = {'started': started, 'advanced': advanced}
        probe.run(window, "document.getElementById('play').click(); document.getElementById('media').currentTime = 1")
        wait_for("(() => {const m = document.getElementById('media'); return m.paused && !m.seeking && Math.abs(m.currentTime - 1) < .05;})()")
        receipt['seek'] = True
        probe.run(window, "document.getElementById('studio-settings').click()")
        wait_for("document.getElementById('settings-dialog').open")
        probe.run(window, "document.getElementById('close-settings').click()")
        screenshot = target.with_suffix('.png')
        capture_screenshot(screenshot)
        if not screenshot.is_file() or screenshot.stat().st_size == 0:
            raise RuntimeError('Native screenshot capture did not produce an image.')
        receipt['screenshot'] = str(screenshot)
        receipt['ok'] = True
    except Exception as error:
        receipt.update(ok=False, error=str(error))
        traceback.print_exc()
    finally:
        if fixture:
            fixture.close()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not receipt.get('screenshot'):
            try:
                screenshot = target.with_suffix('.png')
                capture_screenshot(screenshot)
                if screenshot.is_file() and screenshot.stat().st_size:
                    receipt['screenshot'] = str(screenshot)
            except Exception as error:
                receipt['screenshot_error'] = str(error)
        target.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        window.destroy()


def launch(args, root, data, smoke_receipt):
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Blaze must start its Cocoa interface on the main thread.')
    import webview
    from music_studio.server import Studio, create_server
    from music_studio.downloads import Downloads
    ffmpeg = root / 'bin' / 'ffmpeg'
    if not ffmpeg.is_file():
        raise RuntimeError('The local decoder is missing. Reinstall the complete Blaze app.')
    server = studio = None
    try:
        studio = Studio(data, str(ffmpeg), args.file, root / 'music_studio' / 'models')
        studio.downloader = Downloads(data, root / 'bin', args.downloads_dir)
        server = create_server(studio)
        threading.Thread(target=server.serve_forever, name='BlazeLocalUI', daemon=True).start()
        webview.settings['ALLOW_DOWNLOADS'] = True
        window = webview.create_window('Blaze', f'http://127.0.0.1:{server.server_port}/',
                                       width=1500, height=960, min_size=(780, 600),
                                       background_color='#ffffff')
        studio.native_fullscreen = window.toggle_fullscreen
        if args.ui_smoke:
            webview.start(ui_smoke, (window, studio, args.ui_smoke, smoke_receipt, CocoaProbe()),
                          gui='cocoa', private_mode=False, storage_path=str(data / 'webview'))
            if not smoke_receipt.get('ok'):
                raise RuntimeError(smoke_receipt.get('error', 'The native UI smoke check did not finish.'))
        else:
            webview.start(gui='cocoa', private_mode=False, storage_path=str(data / 'webview'))
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if studio:
            studio.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Blaze for macOS')
    parser.add_argument('file', nargs='?')
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--self-test', metavar='RESULT_JSON')
    checks.add_argument('--ui-smoke', metavar='RESULT_JSON')
    parser.add_argument('--downloads-dir', type=Path, help='Folder for downloaded media')
    parser.add_argument('--data-dir', type=Path, help='Folder for application state')
    args = parser.parse_args(argv)
    root = resource_root()
    if args.self_test:
        package_self_test(args.file, args.self_test, root)
        return 0
    if args.ui_smoke and not args.file:
        parser.error('Provide a local media file for the native UI check.')
    # Automated package checks never touch a user's saved analyses or downloads.
    if args.ui_smoke:
        target = Path(args.ui_smoke).resolve()
        data = target.parent / 'ui-smoke-data'
        args.downloads_dir = data / 'downloads'
    else:
        data = data_directory(args.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    log_path = data / 'desktop.log'
    original_stdout, original_stderr = sys.stdout, sys.stderr
    receipt = {'ok': False, 'platform': sys.platform, 'main_thread': threading.current_thread() is threading.main_thread()}
    status = 0
    with log_path.open('w', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            launch(args, root, data, receipt)
        except Exception as error:
            traceback.print_exc()
            status = 1
            if args.ui_smoke:
                receipt.update(ok=False, error=str(error))
                Path(args.ui_smoke).resolve().write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            else:
                present_error('Reinstall the complete Blaze app if files are missing. Details are saved in ' + str(log_path))
        finally:
            sys.stdout, sys.stderr = original_stdout, original_stderr
    return status


if __name__ == '__main__':
    raise SystemExit(main())
