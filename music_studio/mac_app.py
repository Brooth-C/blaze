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


def ui_smoke(window, studio, destination, receipt, probe, timeout=600):
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
        receipt['controls'] = probe.probe(window, """(() => {
          const ids = ['tab-downloads','tab-studio','tab-library','import','analyze',
            'play','previous','next','loop','speed','instrument','volume','down','up',
            'edit','export-json','export-csv','studio-settings','download-start','download-folder'];
          if (document.documentElement.dataset.presentation === 'mac')
            ids.push('logic-play','logic-chords','logic-arrangement','logic-editor','editor-wave','daw-practice-close');
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
        probe.run(window, "[...document.querySelectorAll('#download-files .download-row')].find(row => row.querySelector('span')?.textContent === " + file_name + ").querySelector('button[aria-label^=\"Open \"]')?.click()")
        wait_for("document.getElementById('downloads-panel').hidden && sourceName === " + file_name + " && document.getElementById('media').readyState >= 1")
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
        if sys.platform == 'darwin':
            probe.run(window, "window.BlazeMac.navigate('studio')")
            wait_for("window.BlazeMacStudio?.snapshot().active === true && window.BlazeMacStudio.snapshot().waveformReady === true")
            receipt['mac_design']['studio_waveform'] = probe.probe(window, 'window.BlazeMacStudio.snapshot()')
            wait_for("window.BlazeLogicVisual?.scope==='live-session' && document.querySelectorAll('#chord-lane button').length > 0")
            harmony = probe.probe(window, """(() => {
              const view=window.BlazeLogicVisual.snapshot(), box=document.getElementById('chord-lane').getBoundingClientRect();
              return {project_timeline:view.duration>0, regions:document.querySelectorAll('#chord-lane button').length,
                visible:box.width>0&&box.height>0&&box.top>=0&&box.bottom<=innerHeight,
                transport_valid:!/(null|NaN|Infinity)/.test(document.getElementById('transport').textContent)};
            })()""")
            if not all(harmony[key] for key in ('project_timeline', 'regions', 'visible', 'transport_valid')):
                raise RuntimeError('The native chord workspace was not usable: ' + json.dumps(harmony))
            receipt['mac_design']['harmony_workspace'] = harmony
            probe.run(window, "window.BlazeMacStudio.commands.practice()")
            wait_for("document.getElementById('daw-chords').getAttribute('aria-expanded')==='true' && !document.getElementById('daw-practice').hidden")
            probe.run(window, "document.getElementById('diagram-strip').scrollIntoView({block:'center'})")
            wait_for("Array.from(document.querySelectorAll('.diagram-card canvas')).every(canvas=>{const r=canvas.getBoundingClientRect();return r.width>0&&r.height>=65&&r.top>=0&&r.bottom<=innerHeight+1;})")
            receipt['mac_design']['chord_drawer'] = {'opened': True, 'keyboards_visible': True,
                                                   'dark_controls': probe.probe(window, "getComputedStyle(document.getElementById('daw-practice')).colorScheme === 'dark'"),
                                                   'count': receipt['diagram_count']}
            capture_screenshot(target.with_name('native-chords.png'))
            probe.run(window, "document.getElementById('daw-practice-close').click()")
            wait_for("document.getElementById('daw-practice').hidden && document.getElementById('daw-chords').getAttribute('aria-expanded')==='false'")
        receipt['layout'] = probe.probe(window, """(() => {
          const viewport = document.documentElement;
          const mac = document.documentElement.dataset.presentation === 'mac';
          const ids = mac ? ['logic-play','logic-chords','logic-arrangement','logic-editor','editor-wave'] : ['bar-flow','diagram-strip','analyze','studio-settings'];
          if (mac && innerWidth >= 1000) ids.push('duplicate-track','add-track');
          return {width: innerWidth, height: innerHeight,
            scroll_height: viewport.scrollHeight,
            studio_workspace: mac && window.BlazeMacStudio?.snapshot().active === true,
            names_fit: !mac || Array.from(document.querySelectorAll('#logic-preview .track-name')).every(name=>name.clientHeight>0),
            editor_toolbar_fits: !mac || document.querySelector('#logic-preview .editor-toolbar').scrollWidth <= document.querySelector('#logic-preview .editor-toolbar').clientWidth + 1,
            branding_fits: mac ? document.querySelector('header').getBoundingClientRect().height===0 : document.querySelector('header .brand h1').getBoundingClientRect().right <= document.querySelector('header').getBoundingClientRect().right,
            controls_visible: ids.every(id => {
              const r = document.getElementById(id).getBoundingClientRect();
              return r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= innerHeight + 1 && r.left >= 0 && r.right <= innerWidth + 1;
            })};
        })()""")
        if (not receipt['layout']['controls_visible'] or not receipt['layout']['branding_fits']
                or not receipt['layout']['names_fit'] or not receipt['layout']['editor_toolbar_fits']
                or receipt['layout']['scroll_height'] > receipt['layout']['height'] + 1):
            raise RuntimeError('The native app layout hides controls or requires vertical scrolling.')
        # Invoke the same handler as the play button. The native media clock,
        # rather than a mocked player response, confirms decoding and movement.
        probe.run(window, "document.getElementById('media').currentTime = 0; document.getElementById(window.BlazeLogicVisual ? 'logic-play' : 'play').click()")
        started = wait_for("(() => {const m = document.getElementById('media'); return !m.paused && m.currentTime > .2 ? m.currentTime : null;})()")
        advanced = wait_for("document.getElementById('media').currentTime", lambda value: value > started + .25)
        receipt['playback'] = {'started': started, 'advanced': advanced}
        probe.run(window, "document.getElementById(window.BlazeLogicVisual ? 'logic-play' : 'play').click(); document.getElementById('media').currentTime = 1")
        wait_for("(() => {const m = document.getElementById('media'); return m.paused && !m.seeking && Math.abs(m.currentTime - 1) < .05;})()")
        receipt['seek'] = True
        probe.run(window, "window.BlazeMac ? window.BlazeMac.action('settings') : document.getElementById('studio-settings').click()")
        wait_for("document.getElementById('settings-dialog').open")
        probe.run(window, "document.getElementById('close-settings').click()")
        wait_for("!document.getElementById('settings-dialog').open")
        # Let the compositor paint the closed dialog before capturing the desktop.
        time.sleep(.2)
        screenshot = target.with_suffix('.png')
        capture_screenshot(screenshot)
        if not screenshot.is_file() or screenshot.stat().st_size == 0:
            raise RuntimeError('Native screenshot capture did not produce an image.')
        receipt['screenshot'] = str(screenshot)
        if sys.platform == 'darwin':
            # Studio collapses the browse sidebar, giving the editor the whole
            # compact content width. The browse sidebar returns on navigation.
            window.resize(780, 600)
            wait_for('innerWidth <= 800 && innerHeight < 600')
            probe.run(window, """window.blazeSmokeLayoutReady=false;
              requestAnimationFrame(()=>requestAnimationFrame(()=>{window.blazeSmokeLayoutReady=true;}));
              true;
            """)
            wait_for('window.blazeSmokeLayoutReady === true')
            compact = probe.probe(window, """(() => {
              const fits = id => {
                const r=document.getElementById(id).getBoundingClientRect();
                return r.width>0&&r.height>0&&r.top>=0&&r.bottom<=innerHeight+1
                  &&r.left>=0&&r.right<=innerWidth+1;
              };
              return {width:innerWidth,height:innerHeight,
                controls:['logic-play','logic-chords','logic-arrangement','logic-editor','editor-wave'].every(fits),
                studio_workspace:window.BlazeMacStudio?.snapshot().active === true,
                no_page_scroll:document.documentElement.scrollHeight<=innerHeight+1,
                no_overflow:document.documentElement.scrollWidth<=innerWidth};
            })()""")
            if not all(compact[key] for key in ('controls', 'studio_workspace', 'no_page_scroll', 'no_overflow')):
                raise RuntimeError('The compact Studio window hides arrangement, waveform or transport controls: ' + json.dumps(compact))
            probe.run(window, "window.BlazeMacStudio.commands.practice()")
            wait_for("!document.getElementById('daw-practice').hidden")
            probe.run(window, "document.getElementById('diagram-strip').scrollIntoView({block:'center'})")
            compact['chord_drawer'] = wait_for("Array.from(document.querySelectorAll('.diagram-card canvas')).every(canvas=>{const r=canvas.getBoundingClientRect();return r.width>0&&r.height>=65&&r.top>=0&&r.bottom<=innerHeight+1;})")
            probe.run(window, "document.getElementById('daw-practice-close').click()")
            wait_for("document.getElementById('daw-practice').hidden")
            receipt['mac_design']['compact_layout'] = compact
            capture_screenshot(target.with_name('native-compact.png'))
        # Use the real platform webview to decode the format prepared by the
        # online player. Chromium test builds can omit these codecs entirely.
        probe.run(window, "window.BlazeDesktop.selectSection('library')")
        video_button = "document.querySelector('button[aria-label=\"Play blaze-video-fixture.mp4\"]')"
        wait_for('!!' + video_button)
        probe.run(window, "window.blazeSmokeVideo = document.getElementById('media'); " + video_button + ".click()")
        wait_for("(() => {const m=document.getElementById('media'); return m.videoWidth===160 && m.videoHeight===90 && !m.paused && m.currentTime>.1;})()")
        if sys.platform == 'darwin':
            probe.run(window, "window.BlazeMac.action('open-player')")
            wait_for("document.getElementById('now-dialog').open")
            fits = probe.probe(window, """(() => {
              return ['now-close','mini-play','mac-mini-seek','now-studio'].every(id=>{
                const r=document.getElementById(id).getBoundingClientRect();
                return r.width>0&&r.height>0&&r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth;
              });
            })()""")
            if not fits:
                raise RuntimeError('The Mac expanded player hides its primary controls below the viewport.')
            receipt['mac_design']['expanded_controls_fit'] = True
        pixels = probe.probe(window, """(() => {
          const c=document.createElement('canvas');c.width=32;c.height=18;
          const g=c.getContext('2d');g.drawImage(document.getElementById('media'),0,0,32,18);
          return g.getImageData(0,0,32,18).data.some((v,i)=>i%4!==3&&v>100);
        })()""")
        if not pixels:
            raise RuntimeError('The native AVC/AAC video frame was blank.')
        probe.run(window, "document.getElementById(window.BlazeMac ? 'mini-play' : 'now-play').click(); document.getElementById('media').currentTime=1")
        wait_for("(() => {const m=document.getElementById('media');return m.paused&&!m.seeking&&Math.abs(m.currentTime-1)<.1;})()")
        capture_screenshot(target.with_name('native-video.png'))
        probe.run(window, "document.getElementById('now-studio').click()")
        wait_for("(() => {const m=document.getElementById('media');return m===window.blazeSmokeVideo && m.parentElement.classList.contains('preview-panel') && m.paused && Math.abs(m.currentTime-1)<.1;})()")
        receipt['video'] = {'codec': 'AVC/AAC', 'decoded_pixels': True, 'studio_return': True,
                            'width': 160, 'height': 90, 'paused_position': 1}
        if sys.platform == 'darwin':
            wait_for("window.BlazeMacStems && !document.getElementById('split-stems').hidden")
            probe.run(window, "document.getElementById('split-stems').click()")
            wait_for("document.getElementById('stems-dialog').open")
            probe.run(window, "document.getElementById('stems-start').click()")
            wait_for("window.BlazeMacStems.snapshot().status==='running' && !document.getElementById('stems-dialog').open")
            interactive = probe.probe(window, "!busy && !document.getElementById('analyze').disabled")
            if not interactive:
                raise RuntimeError('Background separation locked chord analysis.')
            probe.run(window, "window.BlazeMac.search('acoustic sessions', true)")
            wait_for("!document.getElementById('explore-panel').hidden && document.querySelectorAll('#explore-results button').length>0")
            probe.run(window, "window.BlazeMac.navigate('studio')")
            wait_for("!document.getElementById('studio-panel').hidden && !document.getElementById('analyze').disabled")
            separation_active = studio.stems.snapshot()['status'] == 'running'
            if not separation_active:
                raise RuntimeError('The native check did not observe background separation before starting analysis.')
            probe.run(window, "document.getElementById('analyze').click()")
            wait_for("!!result && !busy")
            receipt['background_tasks'] = {'navigation': True, 'fixture_search': True,
                'chord_analysis': True, 'separation_active_at_analysis_start': separation_active,
                'separation_active_after_analysis': studio.stems.snapshot()['status'] == 'running'}
            wait_for("window.BlazeMacStems.snapshot().status==='done' || window.BlazeMacStems.snapshot().status==='failed'")
            separation = probe.probe(window, 'window.BlazeMacStems.snapshot()')
            if separation['status'] != 'done' or len(separation['stems']) != 9:
                raise RuntimeError('The bundled stem model did not complete: ' + json.dumps(separation))
            wait_for("!busy && document.querySelectorAll('#stems-results .stem-result').length===9")
            capture_screenshot(target.with_name('native-stems.png'))
            with studio.lock:
                files = {name: studio.stems.file(separation['jobId'], name) for name in ('vocals', 'drums', 'bass', 'piano', 'guitar', 'strings', 'brass', 'synths', 'other')}
            metadata = {}
            for name, path in files.items():
                result = subprocess.run([str(resource_root() / 'bin/ffprobe'), '-v', 'error',
                                         '-show_entries', 'stream=sample_rate,channels,codec_name:format=duration',
                                         '-of', 'json', str(path)], check=True, capture_output=True, text=True)
                value = json.loads(result.stdout)
                stream = value['streams'][0]
                if stream['sample_rate'] != '44100' or stream['channels'] != 2 or float(value['format']['duration']) < 2:
                    raise RuntimeError('The bundled model produced an invalid WAV stem.')
                metadata[name] = value
            probe.run(window, "document.querySelector('#stems-results button[aria-label=\"Open Vocals in Studio\"]').click()")
            wait_for("!document.getElementById('stems-dialog').open && sourceName==='Vocals.wav' && document.getElementById('media').readyState>=1")
            wait_for("(() => {const s=window.BlazeMacStudio?.snapshot();return s?.active&&s.waveformReady&&s.selectedTrack==='vocals'&&s.tracks.length===9;})()")
            probe.run(window, "document.getElementById('mini-play').click()")
            wait_for("(() => {const m=document.getElementById('media');return m===window.blazeSmokeVideo && !m.paused && m.currentTime>.1;})()")
            receipt['stems'] = {'model': 'BS-RoFormer + Spleeter piano + Mega instrument families', 'count': 9, 'files': metadata,
                                'real_model': True, 'native_playback': True,
                                'studio_workspace': probe.probe(window, 'window.BlazeMacStudio.snapshot()')}
            probe.run(window, "document.getElementById('mini-play').click(); document.getElementById('split-stems').click()")
            wait_for("document.getElementById('stems-dialog').open")
            probe.run(window, "document.querySelector('button[aria-label=\"Open Guitar in Studio\"]').scrollIntoView({block:'center'})")
            wait_for("""(() => {
              const row=document.querySelector('button[aria-label="Open Guitar in Studio"]').getBoundingClientRect();
              const list=document.getElementById('stems-results').getBoundingClientRect();
              return row.top>=list.top&&row.bottom<=list.bottom&&row.width>0;
            })()""")
            probe.run(window, "document.querySelector('button[aria-label=\"Open Guitar in Studio\"]').click()")
            wait_for("!document.getElementById('stems-dialog').open && sourceName==='Guitar.wav' && document.getElementById('media').readyState>=1")
            wait_for("(() => {const s=window.BlazeMacStudio?.snapshot();return s?.active&&s.waveformReady&&s.selectedTrack==='guitar'&&s.tracks.length===9;})()")
            probe.run(window, "document.getElementById('mini-play').click()")
            wait_for("(() => {const m=document.getElementById('media');return m===window.blazeSmokeVideo && !m.paused && m.currentTime>.1;})()")
            receipt['stems']['instrument_playback'] = True
            probe.run(window, "document.getElementById('mini-play').click(); document.getElementById('split-stems').click()")
            wait_for("document.getElementById('stems-dialog').open")
            probe.run(window, "document.getElementById('stems-piano').click()")
            wait_for("window.BlazeMacStems.snapshot().mode==='piano' && ['done','failed'].includes(window.BlazeMacStems.snapshot().status)")
            piano_job = probe.probe(window, 'window.BlazeMacStems.snapshot()')
            if piano_job['status'] != 'done' or {row['id'] for row in piano_job['stems']} != {'piano', 'accompaniment'}:
                raise RuntimeError('Bundled piano isolation failed: ' + json.dumps(piano_job))
            wait_for("!busy && document.querySelectorAll('#stems-results .stem-result').length===2")
            capture_screenshot(target.with_name('native-piano.png'))
            probe.run(window, "document.querySelector('button[aria-label=\"Open Piano in Studio\"]').click()")
            wait_for("!document.getElementById('stems-dialog').open && sourceName==='Piano.wav' && document.getElementById('media').readyState>=1")
            probe.run(window, "document.getElementById('mini-play').click()")
            wait_for("(() => {const m=document.getElementById('media');return m===window.blazeSmokeVideo && !m.paused && m.currentTime>.1;})()")
            receipt['piano'] = {'model': 'Spleeter 5stems', 'real_model': True, 'native_playback': True, 'outputs': 2}
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
