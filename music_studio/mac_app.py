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


class SmokeCatalogue:
    """Network-free metadata fixture, only installed by explicit --ui-smoke.

    Packaged UI checks exercise a real local download and real playback/analysis.
    Detailed catalogue behavior is covered by the separate provider-contract and
    browser suites; startup must never depend on a live YouTube request.
    """
    def request(self, body):
        return {'requestId': 'native-smoke'}

    def status(self, identity):
        return {'status': 'ready', 'items': [], 'error': None, 'progress': 'Controlled native fixture.'}

    def history(self):
        return []

    def cancel(self, identity):
        pass

    def listened(self, body):
        pass

    def reset(self):
        pass

    def close(self):
        pass


def capture_screenshot(destination):
    if sys.platform == 'darwin':
        subprocess.run(['/usr/sbin/screencapture', '-x', str(destination)], check=True, timeout=15)
    else:
        from PIL import ImageGrab
        ImageGrab.grab().save(destination)


def native_piano_identity():
    # PyInstaller executes this file as an entrypoint, without a package parent.
    from music_studio.native_piano_assets import HEAD, CHECKPOINT_SHA
    from music_studio.piano_backend import selected_piano_backend
    backend = selected_piano_backend()
    result = {'model': 'Mega53 native acoustic piano', 'checkpoint_sha256': CHECKPOINT_SHA,
              'head_sha256': HEAD['sha256'], 'backend': backend}
    if backend == 'mlx':
        from music_studio.mlx_piano_assets import WEIGHTS
        result['mlx_weights_sha256'] = WEIGHTS['sha256']
    return result


def ui_smoke(window, studio, destination, receipt, probe, timeout=900):
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
        if sys.platform == 'darwin':
            from PyObjCTools import AppHelper
            from Foundation import NSIndexSet
            wait_for("document.body.dataset.nativeSidebar === 'true' && !!window.BlazeMac")
            chrome = studio.native_navigation
            if not chrome.receipt.get('installed'):
                raise RuntimeError('The native Mac navigation was not installed.')

            def select_downloads():
                row = chrome.row_for_section('downloads')
                chrome.outline.selectRowIndexes_byExtendingSelection_(
                    NSIndexSet.indexSetWithIndex_(row), False)

            AppHelper.callAfter(select_downloads)
            wait_for("window.BlazeDesktop.activeSection() === 'downloads'")
            probe.run(window, "window.BlazeMac.navigate('studio')")
            wait_for("window.BlazeDesktop.activeSection() === 'studio'")
            while chrome.receipt.get('selected') != 'studio' and time.monotonic() < deadline:
                time.sleep(.1)
            if chrome.receipt.get('selected') != 'studio':
                raise RuntimeError('Web navigation did not synchronize with native navigation.')
            receipt['native_navigation'] = dict(chrome.receipt, roundtrip=True)
            wait_for("!!sourceName")

            def native_search():
                chrome.focus_search()
                field = chrome.search_item.searchField()
                field.setStringValue_('acoustic')
                field.sendAction_to_(field.action(), field.target())

            AppHelper.callAfter(native_search)
            wait_for("window.BlazeDesktop.activeSection()==='explore' && document.getElementById('explore-results').textContent.toLowerCase().includes('acoustic') && document.querySelectorAll('.discovery-card').length>0")
            capture_screenshot(target.with_name('native-search.png'))
            probe.run(window, "document.querySelector('.discovery-primary').click()")
            wait_for("(() => {const m=document.getElementById('media');return !m.paused&&m.currentTime>.1;})()")
            if probe.probe(window, "document.getElementById('now-dialog').open || window.BlazeDesktop.activeSection()!=='explore'"):
                raise RuntimeError('Selecting a Mac recording interrupted browsing with the expanded player.')
            probe.run(window, "document.getElementById('mini-play').click()")
            wait_for("document.getElementById('media').paused")
            probe.run(window, "window.BlazeMac.search('')")
            wait_for("document.querySelectorAll('.discovery-featured').length===3")
            wait_for("document.querySelectorAll('.discovery-featured img').length===3 && Array.from(document.querySelectorAll('.discovery-featured img')).every(image=>image.complete&&image.naturalWidth>0)")
            probe.run(window, """window.blazeSmokeArtReady=false;
              Promise.all(Array.from(document.querySelectorAll('.discovery-featured img')).map(image=>image.decode()))
                .then(()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{window.blazeSmokeArtReady=true;})));
              true;
            """)
            wait_for('window.blazeSmokeArtReady === true')
            capture_screenshot(target.with_name('native-explore.png'))
            receipt['mac_design'] = {
                'sidebar': True, 'native_search': True, 'compact_player': True,
                'controlled_metadata': True, 'selection_keeps_browsing': True,
            }
            probe.run(window, "window.BlazeMac.navigate('studio')")
            wait_for("window.BlazeDesktop.activeSection()==='studio'")
            wait_for("window.BlazeMacPractice?.snapshot().visible === true")
            receipt['practice'] = {'default': True}
            capture_screenshot(target.with_name('native-practice.png'))
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
        probe.run(window, "[...document.querySelectorAll('#download-files .download-row')].find(row => row.querySelector('span')?.textContent === " + file_name + ").querySelector('button[aria-label^=\"Open \"]')?.click()")
        wait_for("document.getElementById('downloads-panel').hidden && sourceName === " + file_name + " && document.getElementById('media').readyState >= 1")
        with studio.lock:
            if studio.source != downloaded_path:
                raise RuntimeError('Open in Studio did not select the downloaded WAV file.')
        fixture.close()
        fixture = None

        wait_for("window.BlazeMacPractice.snapshot().visible && window.BlazePracticeEngine.snapshot().waveformReady")
        probe.run(window, "window.blazePracticeMedia=document.getElementById('media'); document.getElementById('practice-piano').click()")
        wait_for("window.BlazeMacPractice.snapshot().preparing")
        if studio.stems.snapshot()['status'] != 'running':
            raise RuntimeError('The native test did not observe background piano preparation.')
        probe.run(window, "window.BlazeMac.navigate('explore'); window.BlazeMac.search('acoustic sessions',true)")
        wait_for("document.querySelectorAll('#explore-results .discovery-card').length>0")
        probe.run(window, "window.BlazeMac.navigate('studio')")
        wait_for("window.BlazeMacPractice.snapshot().visible")
        active_at_analysis = studio.stems.snapshot()['status'] == 'running'
        if not active_at_analysis:
            raise RuntimeError('The native check missed concurrent preparation and analysis.')
        with studio.lock:
            analysis_key = studio.source_identity(studio.source)
        probe.run(window, "document.getElementById('practice-analyze').click()")
        wait_for("!busy && window.BlazePracticeEngine.viewState().analysisTask?.status==='done'")
        with studio.lock:
            recognition = studio.analysis_results.get(analysis_key)
        if not recognition or not recognition.get('chords'):
            raise RuntimeError('Background recognition did not retain the original song guide.')
        receipt['model'] = recognition['model']
        receipt['chords'] = len(recognition['chords'])
        receipt['engine_version'] = recognition['engine_version']
        receipt['background_tasks'] = {'navigation': True, 'fixture_search': True, 'chord_analysis': True,
            'separation_active_at_analysis_start': active_at_analysis}
        wait_for("!!window.BlazeMacPractice.snapshot().pianoJobId && !window.BlazeMacPractice.snapshot().preparing && window.BlazeMacPractice.snapshot().mode==='piano'")
        for listening_mode in ('original', 'piano', 'backing'):
            button = json.dumps('practice-' + listening_mode)
            ready = "(() => {const b=document.getElementById(" + button + ");return b && !b.disabled && b.getAttribute('aria-busy')!=='true';})()"
            wait_for(ready)
            probe.run(window, "document.getElementById(" + button + ").click()")
            wait_for("window.BlazeMacPractice.snapshot().mode===" + json.dumps(listening_mode) +
                     " && !window.BlazePracticeEngine.viewState().pending && " + ready)
        probe.run(window, "document.getElementById('practice-play').click()")
        wait_for("!document.getElementById('media').paused && document.getElementById('media').currentTime>.1")
        receipt['piano'] = {**native_piano_identity(), 'real_model': True, 'native_playback': True, 'outputs': 2}
        probe.run(window, "document.getElementById('media').pause(); document.getElementById('practice-pitch-up').click()")
        wait_for("window.BlazeMacPractice.snapshot().transpose===1 && !window.BlazeMacPractice.snapshot().pitchBusy")
        pitch = probe.probe(window, "({samePlayer:window.blazePracticeMedia===document.getElementById('media'), localAudio:document.getElementById('media').src.includes('/api/practice-audio'), transpose:window.BlazeMacPractice.snapshot().transpose})")
        if not pitch['samePlayer'] or not pitch['localAudio']:
            raise RuntimeError('Native transpose did not use the single local player.')
        receipt['transpose'] = pitch
        probe.run(window, "document.getElementById('practice-pitch-reset').click()")
        wait_for("window.BlazeMacPractice.snapshot().transpose===0 && !window.BlazeMacPractice.snapshot().pitchBusy")
        probe.run(window, "window.blazeExport=null; api('/api/practice-render',{kind:'both',semitones:0,sourceRevision,jobId:window.BlazeMacPractice.snapshot().pianoJobId}).then(value=>window.blazeExport=value); true")
        wait_for("!!window.blazeExport")
        export_id = probe.probe(window, 'window.blazeExport.requestId')
        exported = {'status': 'pending'}
        while time.monotonic() < deadline:
            exported = studio.practice_audio.status(export_id)
            if exported['status'] != 'pending':
                break
            time.sleep(.1)
        if exported['status'] != 'ready':
            raise RuntimeError('Native WAV bundle did not finish.')
        import zipfile
        with zipfile.ZipFile(studio.practice_audio.file(export_id)[0]) as archive:
            if set(archive.namelist()) != {'Piano.wav', 'Backing.wav'}:
                raise RuntimeError('Native WAV bundle did not contain both separate tracks.')
        receipt['exports'] = {'piano': True, 'backing': True, 'separateWavsInZip': True}
        probe.run(window, "window.BlazePracticeEngine.commands.seek(.2); document.getElementById('practice-set-a').click(); window.BlazePracticeEngine.commands.seek(.8); document.getElementById('practice-set-b').click(); document.querySelector('#practice-workspace [data-rate=\".75\"]').click(); document.getElementById('practice-save').click()")
        wait_for("!!window.BlazeMacPractice.snapshot().sessionId && !window.BlazeMacPractice.snapshot().saving")
        practice = probe.probe(window, "({...window.BlazeMacPractice.snapshot(),singlePlayer:document.querySelectorAll('audio,video').length===1, advancedRemoved:!document.querySelector('#logic-preview,#mac-studio-workspace,#practice-advanced')})")
        if not (practice['singlePlayer'] and practice['advancedRemoved'] and practice['pitchPreserved'] and practice['loopEnabled'] and practice['rate']==.75):
            raise RuntimeError('Native Practice controls failed: ' + json.dumps(practice))
        receipt['practice'].update(practice, modes=['original', 'piano', 'backing'])
        probe.run(window, "document.querySelector('.practice-content').scrollTop=0")
        capture_screenshot(target.with_name('native-practice.png'))
        window.resize(780, 600)
        time.sleep(.3)
        layout = probe.probe(window, "({practice:window.BlazeMacPractice.snapshot().visible,noAdvanced:!document.querySelector('#logic-preview,#mac-studio-workspace,#practice-advanced'),noOverflow:document.documentElement.scrollWidth<=innerWidth+1, controls:['practice-open','practice-find','practice-play'].every(id=>{const b=document.getElementById(id).getBoundingClientRect();return b.width>0&&b.left>=0&&b.right<=innerWidth+1&&b.bottom<=innerHeight+1;})})")
        if not all(layout.values()):
            raise RuntimeError('The compact Practice layout failed: ' + json.dumps(layout))
        receipt['layout'] = layout
        capture_screenshot(target.with_name('native-compact.png'))
        capture_screenshot(target.with_suffix('.png'))
        receipt['screenshot'] = str(target.with_suffix('.png'))
        receipt['ok'] = True
    except Exception as error:
        receipt.update(ok=False, error=str(error))
        try:
            receipt['failure_state'] = probe.probe(window, "({sourceRevision, sourceName, "
                "practice:window.BlazeMacPractice?.snapshot(), studio:window.BlazeMacStudio?.snapshot(), "
                "pending:window.BlazeMacStudio?.viewState().pending})")
            capture_screenshot(target.with_name('native-failure.png'))
        except Exception as diagnostic_error:
            receipt['failure_state_error'] = str(diagnostic_error)
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
    server = studio = native_navigation = None
    try:
        studio = Studio(data, str(ffmpeg), args.file, root / 'music_studio' / 'models')
        studio.presentation = 'mac'
        studio.downloader = Downloads(data, root / 'bin', args.downloads_dir)
        if args.ui_smoke:
            from music_studio.mac_smoke import MacSmokeCatalogue
            studio.discovery = MacSmokeCatalogue(data, args.file)
            smoke_receipt['discovery_fixture'] = True
        server = create_server(studio)
        threading.Thread(target=server.serve_forever, name='BlazeLocalUI', daemon=True).start()
        webview.settings['ALLOW_DOWNLOADS'] = True
        window = webview.create_window('Blaze', f'http://127.0.0.1:{server.server_port}/',
                                       width=1280, height=820, min_size=(780, 600),
                                       background_color='#ffffff')
        studio.native_fullscreen = window.toggle_fullscreen
        try:
            from music_studio.mac_chrome import attach_navigation
            native_navigation = studio.native_navigation = attach_navigation(
                window, smoke_receipt.setdefault('native_navigation', {}), on_import=studio.open_local_file)
        except ImportError as error:
            # The underlying web navigation remains usable if a bridge package
            # is unavailable; native package checks still report this failure.
            smoke_receipt['native_navigation'] = {'installed': False, 'error': str(error)}
        if args.ui_smoke:
            webview.start(ui_smoke, (window, studio, args.ui_smoke, smoke_receipt, CocoaProbe()),
                          gui='cocoa', private_mode=False, storage_path=str(data / 'webview'))
            if not smoke_receipt.get('ok'):
                raise RuntimeError(smoke_receipt.get('error', 'The native UI smoke check did not finish.'))
        else:
            webview.start(gui='cocoa', private_mode=False, storage_path=str(data / 'webview'))
    finally:
        if native_navigation is not None:
            native_navigation.stop()
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
