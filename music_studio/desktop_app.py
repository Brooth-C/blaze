"""Windows and Linux desktop launcher with isolated native package checks."""
from pathlib import Path
import argparse
import json
import os
import sys
import threading
import traceback


class NativeProbe:
    """Call the renderer directly; never use eval or relax the page CSP."""
    def _evaluate(self, window, source):
        # start(func) runs before WebView2 has necessarily finished navigation.
        # Executing against an uninitialized controller can leave its task pending.
        if not window.events.loaded.wait(30):
            raise RuntimeError('The native page did not finish loading.')
        finished = threading.Event()
        result = {}

        def evaluate():
            try:
                result['value'] = window.gui.evaluate_js(source, window.uid, False)
            except Exception as error:
                result['error'] = error
            finally:
                finished.set()

        threading.Thread(target=evaluate, name='BlazeNativeProbe', daemon=True).start()
        if not finished.wait(10):
            raise RuntimeError('The native renderer did not answer within ten seconds.')
        if 'error' in result:
            raise result['error']
        text = result['value']
        if not isinstance(text, str):
            raise RuntimeError('The native renderer did not return a probe result.')
        response = json.loads(text)
        if not response.get('ok'):
            raise RuntimeError(response.get('error', 'Native JavaScript probe failed'))
        return response.get('value')

    def run(self, window, script):
        return self._evaluate(window, 'JSON.stringify((()=>{try{' + script +
                              ';return {ok:true};}catch(e){return {ok:false,error:String(e)};}})())')

    def probe(self, window, expression):
        return self._evaluate(window, 'JSON.stringify((()=>{try{return {ok:true,value:(' + expression +
                              ')};}catch(e){return {ok:false,error:String(e)};}})())')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Blaze desktop')
    parser.add_argument('file', nargs='?')
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument('--self-test')
    checks.add_argument('--ui-smoke')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--downloads-dir', type=Path)
    args = parser.parse_args(argv)
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    windows = sys.platform == 'win32'
    decoder = root / 'bin' / ('ffmpeg.exe' if windows else 'ffmpeg')
    models = root / 'music_studio/models'
    if args.self_test:
        from music_studio.engine import ModelBundle, Analyzer
        from music_studio.store import Store, export_json, export_csv
        if not args.file:
            parser.error('Provide local media for the package self-test.')
        target = Path(args.self_test).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        result = Analyzer(ModelBundle(models), str(decoder)).analyze(args.file)
        store = Store(target.parent / 'self-test-data')
        result = store.edit(store.save(result), 0, 'C:maj')
        target.write_bytes(export_json(result))
        target.with_suffix('.csv').write_bytes(export_csv(result))
        return 0
    if args.ui_smoke:
        if not args.file:
            parser.error('Provide local media for the native interface check.')
        data = Path(args.ui_smoke).resolve().parent / 'ui-smoke-data'
        args.downloads_dir = data / 'downloads'
    elif args.data_dir:
        data = args.data_dir.resolve()
    elif windows:
        data = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BlazeMusicStudio'
    else:
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'Blaze'
    data.mkdir(parents=True, exist_ok=True)
    receipt = {'ok': False, 'platform': sys.platform}
    server = studio = None
    original_out, original_error = sys.stdout, sys.stderr
    status = 0
    with (data / 'desktop.log').open('w', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            import webview
            from music_studio.server import Studio, create_server
            from music_studio.downloads import Downloads
            if not decoder.is_file():
                raise RuntimeError('The decoder is missing. Reinstall Blaze; Linux also requires FFmpeg.')
            if windows:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BroothC.Blaze')
            studio = Studio(data, str(decoder), args.file, models)
            studio.downloader = Downloads(data, root / 'bin', args.downloads_dir)
            if args.ui_smoke:
                from music_studio.mac_app import SmokeCatalogue
                studio.discovery = SmokeCatalogue()
                receipt['discovery_fixture'] = True
            server = create_server(studio)
            threading.Thread(target=server.serve_forever, name='BlazeLocalUI', daemon=True).start()
            webview.settings['ALLOW_DOWNLOADS'] = True
            renderer = 'edgechromium' if windows else 'gtk'
            # Select the same backend for screen discovery and the actual window.
            os.environ['PYWEBVIEW_GUI'] = renderer
            screen = webview.screens[0]
            width = min(1500, max(780, screen.width - 40))
            height = min(960, max(600, screen.height - 100))
            window = webview.create_window('Blaze', f'http://127.0.0.1:{server.server_port}/',
                                            width=width, height=height, min_size=(780, 600),
                                            background_color='#ffffff')
            studio.native_fullscreen = window.toggle_fullscreen
            options = dict(gui=renderer, private_mode=False, storage_path=str(data / 'webview'))
            if args.ui_smoke:
                from music_studio.mac_app import ui_smoke
                webview.start(ui_smoke, (window, studio, args.ui_smoke, receipt, NativeProbe()), **options)
                if not receipt.get('ok'):
                    raise RuntimeError(receipt.get('error', 'Native UI verification did not finish.'))
            else:
                webview.start(**options)
        except Exception as error:
            status = 1
            traceback.print_exc()
            receipt.update(ok=False, error=str(error))
            if args.ui_smoke:
                Path(args.ui_smoke).resolve().write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            elif windows:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, 'Blaze could not open. Check ' + str(data / 'desktop.log') +
                                               '. Microsoft Edge WebView2 Runtime is required.', 'Blaze', 16)
            else:
                print('Blaze could not open. See ' + str(data / 'desktop.log'), file=original_error)
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if studio:
                studio.close()
            sys.stdout, sys.stderr = original_out, original_error
    return status
