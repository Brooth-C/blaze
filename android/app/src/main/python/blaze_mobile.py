"""APK downloader: embedded yt-dlp, no terminal or external executables."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL


class DownloadCancelled(Exception):
    pass


def validate_url(url):
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Paste a complete HTTPS link without login credentials.")
    return url.strip()


def download(url, mode, directory, callback):
    url = validate_url(url)
    if mode not in ("video", "audio"):
        raise ValueError("Choose video or audio.")
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    def check_cancel():
        if callback.isCancelled():
            raise DownloadCancelled("Download stopped. Retry the same link to resume.")

    def progress(data):
        check_cancel()
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        done = data.get("downloaded_bytes") or 0
        percent = min(100, done * 100 / total) if total else -1
        callback.onProgress(float(percent), "Saving file…" if data["status"] == "finished" else "Downloading…")

    options = {
        "format": "bestaudio/best" if mode == "audio" else "best[vcodec!=none][acodec!=none]/best",
        "outtmpl": str(folder / "%(title).120B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "continuedl": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "progress_hooks": [progress],
        "quiet": True,
        "no_warnings": True,
        "ignoreconfig": True,
        "fixup": "never",
        "postprocessors": [],
        "cachedir": False,
    }
    check_cancel()
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
        check_cancel()
        if not info or info.get("_type") in ("playlist", "multi_video"):
            raise ValueError("Use a link to one video or audio item.")
        if mode == "video" and (info.get("vcodec") == "none" or info.get("acodec") == "none"):
            raise ValueError("No video stream with sound is available. Try audio mode or the Termux version.")
        downloader.process_info(info)
        check_cancel()
        filename = Path(downloader.prepare_filename(info)).resolve()
        if filename.parent != folder or not filename.is_file():
            raise ValueError("The download did not produce a complete file.")
        return json.dumps({"path": str(filename), "title": info.get("title", filename.name)})
