"""Portable Windows desktop entry point; no runtime downloads."""
from pathlib import Path
import argparse
import ctypes
import os
import sys
import threading
import traceback


def main():
    parser = argparse.ArgumentParser(description="Blaze for Windows")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--self-test", metavar="RESULT_JSON")
    parser.add_argument("--downloads-dir", type=Path, help="Folder for downloaded media")
    parser.add_argument("--data-dir", type=Path, help="Folder for application state")
    args = parser.parse_args()
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    ffmpeg = root / "bin" / "ffmpeg.exe"
    models = root / "music_studio" / "models"
    data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BlazeMusicStudio"
    if args.data_dir:
        data = args.data_dir.resolve()
    # Automated package checks use an explicitly isolated directory.
    if args.self_test:
        from music_studio.engine import ModelBundle, Analyzer
        from music_studio.store import Store, export_json, export_csv
        if not args.file:
            raise ValueError("Provide a local media file for the package self-test.")
        result = Analyzer(ModelBundle(models), str(ffmpeg)).analyze(args.file)
        target = Path(args.self_test).resolve()
        store = Store(target.parent / "self-test-data")
        result = store.save(result)
        result = store.edit(result, 0, "C:maj")
        target.write_bytes(export_json(result))
        target.with_suffix(".csv").write_bytes(export_csv(result))
        return
    data.mkdir(parents=True, exist_ok=True)
    log = (data / "desktop.log").open("w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    server = studio = None
    try:
        import webview
        from music_studio.server import Studio, create_server
        from music_studio.downloads import Downloads
        if not ffmpeg.is_file():
            raise RuntimeError("The local decoder is missing. Extract the complete Blaze folder from the ZIP.")
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BroothC.Blaze")
        studio = Studio(data, str(ffmpeg), args.file, models)
        studio.downloader = Downloads(data, root / 'bin', args.downloads_dir)
        server = create_server(studio)
        worker = threading.Thread(target=server.serve_forever, name="BlazeLocalUI", daemon=True)
        worker.start()
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window("Blaze", f"http://127.0.0.1:{server.server_port}/",
                              width=1500, height=960, min_size=(780, 600), background_color="#10131c")
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(data / "webview"))
    except Exception:
        traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None,
            "Blaze could not open. Extract the complete ZIP first. Microsoft Edge WebView2 Runtime is required. "
            "Details are saved in " + str(data / "desktop.log"), "Blaze", 16)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if studio:
            studio.close()
        log.close()


if __name__ == "__main__":
    main()
