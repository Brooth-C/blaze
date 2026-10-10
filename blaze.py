#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blaze — private audio/video downloader with a responsive terminal dashboard.
Requires Python 3.10+ for source use; installers provide a managed Python runtime.

Usage:
    python blaze.py
    python blaze.py --mode audio -F mp3 "URL"
    python blaze.py --mode video --video-resolution 1080p "URL"
    python blaze.py --doctor

Owned dependencies and configuration stay under ~/Blaze. Media downloads go
under OUTPUT/Audio or OUTPUT/Video; reports are URL-job results, not independent
playlist-completeness audits. Rerun a command to resume interrupted downloads.
WAV/FLAC conversion cannot restore detail absent from a lossy source.

Regression and local-media integration tests live beside this file. Target-OS
installer tests run separately in GitHub Actions. Passing checks are evidence
for those scenarios, not a guarantee about every public-service extractor.
"""

import os
import re
import sys
import json
import time
import signal
import shutil
import argparse
import subprocess
import concurrent.futures
import threading
import platform
import urllib.request
import tempfile
import tarfile
import shlex
import uuid
import queue
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, fields, replace
from typing import List, Optional, Tuple, Dict
from collections import deque
from functools import wraps
from contextlib import contextmanager
import errno
import math
import hashlib
import zipfile

# ═══════════════════════════════════════════════════════════════════════
# METADATA
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "Blaze"
VERSION = "4.1.23"
DEFAULT_WORKERS = 4
DEFAULT_FRAGMENTS = 8
DEFAULT_OUTPUT = Path.home() / "Blaze"
LEGACY_OUTPUTS = {
    str(Path.home() / "Music" / "BlazeDownloads"),
    str(Path.home() / "BlazeDownloads"),
}
BLAZE_RUNTIME_DIR = DEFAULT_OUTPUT / ".runtime"
CONFIG_DIR = DEFAULT_OUTPUT / "Config"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCAL_BIN_DIR = BLAZE_RUNTIME_DIR / "bin"
BLAZE_VENV_DIR = BLAZE_RUNTIME_DIR / "venv"
BLAZE_STATE_DIR = BLAZE_RUNTIME_DIR / "state"

# Pinned portable binaries; verify SHA-256 before extraction or execution.
ARIA2_MAC_BASE = "https://github.com/Brooth-C/blaze/releases/download/aria2-macos-1.37.0-1"
ARIA2_ARTIFACTS = {
    ("darwin", "arm64"): (f"{ARIA2_MAC_BASE}/aria2c-1.37.0-macos-arm64", "f17b4e835968484a1fa25bb3c6b589bb22c4b74f08deb9b4fb93bd81eb1dc70f", False),
    ("darwin", "x64"): (f"{ARIA2_MAC_BASE}/aria2c-1.37.0-macos-x64", "8243d9d999dcb4b0898015b326203f916663571f0cc5802c01d39db0d781ab87", False),
    ("win32", "x64"): (
        "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip",
        "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288", True),
    ("linux", "x64"): (
        "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-x86_64-linux-musl_static.zip",
        "e0a09b12ef67f35f8a8e4fdddbec851d235b7c31da549d0578bff459032b499a", True),
    ("linux", "arm64"): (
        "https://github.com/abcfy2/aria2-static-build/releases/download/1.37.0/aria2-aarch64-linux-musl_static.zip",
        "0c681a89a40e0f82d1f5137608e86257eb0af201459c002941ea098f2b8c26b6", True),
}

ALLOWED_AUDIO_FORMATS = {"wav", "flac", "mp3", "opus", "m4a", "ogg"}
ALLOWED_VIDEO_FORMATS = {"mp4", "mkv", "best"}
SPEED_PRESETS = {"safe", "fast", "max"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}

# Audio-only / likely-audio sites
AUDIO_ONLY_HOSTS = {"soundcloud.com", "bandcamp.com", "mixcloud.com", "listenbrainz.org"}
# Known video platforms
VIDEO_HOSTS = {"youtube.com", "youtu.be", "instagram.com", "tiktok.com", "twitter.com", "x.com", "reddit.com", "vimeo.com", "facebook.com", "fb.com", "twitch.tv", "dailymotion.com", "vm.tiktok.com"}

# Speed preset defaults
SPEED_CONFIG = {
    "safe": {"workers": 2, "fragments": 4, "aria_connections": 8, "aria_segments": 8},
    "fast": {"workers": 4, "fragments": 8, "aria_connections": 16, "aria_segments": 16},
    "max": {"workers": 8, "fragments": 16, "aria_connections": 16, "aria_segments": 16},
}


def _valid_audio_quality(value: str) -> bool:
    """yt-dlp expects audio quality between 0 and 10. 0 is best/largest, 10 is smallest/worst."""
    try:
        q = float(value)
    except (TypeError, ValueError):
        return False
    return 0.0 <= q <= 10.0


# ═══════════════════════════════════════════════════════════════════════
# ANSI COLORS & STYLES
# ═══════════════════════════════════════════════════════════════════════

class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


# ═══════════════════════════════════════════════════════════════════════
# LOGGING SYSTEM
# ═══════════════════════════════════════════════════════════════════════

class Logger:
    QUIET = False
    NO_COLOR = False
    _dashboard_tracker = None

    @classmethod
    @contextmanager
    def dashboard(cls, tracker):
        previous = cls._dashboard_tracker
        cls._dashboard_tracker = tracker
        try:
            yield
        finally:
            cls._dashboard_tracker = previous

    @classmethod
    def _out(cls, symbol: str, color: str, title: str, message: str):
        if cls.QUIET:
            return
        if cls._dashboard_tracker is not None:
            cls._dashboard_tracker.add_log(f"{title.lower()}: {message}")
            return
        ts = datetime.now().strftime("%H:%M:%S")
        if cls.NO_COLOR:
            print(f"[{ts}] {symbol} {title}: {message}", flush=True)
        else:
            print(f"{Style.DIM}[{ts}]{Style.RESET} {color}{symbol}{Style.RESET} {Style.BOLD}{title}:{Style.RESET} {message}", flush=True)

    @classmethod
    def info(cls, msg: str):
        cls._out("i", Style.BLUE, "INFO", msg)

    @classmethod
    def success(cls, msg: str):
        cls._out("+", Style.GREEN, "DONE", msg)

    @classmethod
    def warn(cls, msg: str):
        cls._out("!", Style.YELLOW, "WARN", msg)

    @classmethod
    def error(cls, msg: str):
        if cls._dashboard_tracker is not None:
            cls._dashboard_tracker.add_log(f"error: {msg}")
            return
        print(f"FAIL: {msg}", file=sys.stderr, flush=True)

    @classmethod
    def banner(cls):
        if cls.QUIET:
            return
        columns = max(1, shutil.get_terminal_size((80, 24)).columns)
        width = min(58, columns - 4)
        if cls.NO_COLOR or width < 48:
            print(f"Blaze v{VERSION}"[:columns] + "\n")
            return
        bc = Style.CYAN + Style.BOLD
        rst = Style.RESET
        text1 = f"{Style.BOLD}Blaze{rst} v{VERSION}{Style.DIM} - Universal Terminal Downloader{rst}"
        subtitle = ("Audio & video · Private installation · Resume support" if width >= 55
                    else "Audio · Video · Private runtime · Resume")
        text2 = f"{Style.DIM}{subtitle}{rst}"

        def _pad(s, w):
            clean = re.sub(r"\x1B\[[0-9;]*m", "", s)
            return s + " " * max(0, w - len(clean))

        print("\n" + bc + "╔" + "═" * width + "╗" + rst)
        print(bc + "║ " + rst + _pad(text1, width - 2) + " " + bc + "║" + rst)
        print(bc + "║ " + rst + _pad(text2, width - 2) + " " + bc + "║" + rst)
        print(bc + "╚" + "═" * width + "╝" + rst + "\n")


# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION MANAGER
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    output_dir: str = str(DEFAULT_OUTPUT)
    workers: int = DEFAULT_WORKERS
    fragments: int = DEFAULT_FRAGMENTS
    use_aria2c: bool = True
    audio_quality: str = "0"
    format: str = "wav"
    mode: str = "auto"
    retries: int = 3
    write_metadata: bool = True
    write_thumbnails: bool = True
    write_subtitles: bool = False
    create_subdirs: bool = True
    tui_refresh_rate: int = 8
    insecure: bool = False
    speed: str = "fast"
    cookies_file: str = ""
    cookies_browser: str = ""
    video_format: str = "mp4"
    video_resolution: str = ""
    ignore_history: bool = False

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            Logger.warn(f"Cannot create config directory: {e}")
            return
        tmp = CONFIG_FILE.with_name(f".{CONFIG_FILE.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
            for _ in range(3):
                try:
                    tmp.replace(CONFIG_FILE)
                    break
                except PermissionError:
                    time.sleep(0.1)
            else:
                tmp.replace(CONFIG_FILE)
        except PermissionError:
            Logger.warn("Cannot save config — file locked by another process")
        except OSError as e:
            Logger.warn(f"Cannot save config: {e}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def load(cls) -> "Config":
        defaults = cls()
        legacy_config = Path.home() / ".config" / APP_NAME.lower() / "config.json"
        source = CONFIG_FILE if CONFIG_FILE.is_file() else legacy_config
        if source.is_file():
            try:
                with open(source, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Config must be a JSON object")
                known = {f.name for f in fields(cls)}
                filtered = {k: v for k, v in data.items() if k in known}

                int_fields = ("workers", "fragments", "retries", "tui_refresh_rate")
                bool_fields = ("use_aria2c", "write_metadata", "write_thumbnails", "write_subtitles", "create_subdirs", "insecure", "ignore_history")
                str_fields = ("output_dir", "audio_quality", "format", "mode", "speed", "cookies_file", "cookies_browser", "video_format", "video_resolution")

                for key in int_fields:
                    if key in filtered:
                        val = filtered[key]
                        if isinstance(val, bool) or not isinstance(val, int):
                            filtered.pop(key)
                        elif val < 0 and key != "retries":
                            filtered.pop(key)
                        elif val < 0:
                            filtered.pop(key)

                for key in bool_fields:
                    if key in filtered and not isinstance(filtered[key], bool):
                        filtered.pop(key)

                for key in str_fields:
                    if key not in filtered:
                        continue
                    value = filtered[key]
                    if value is None or not isinstance(value, str) or not value.strip():
                        filtered.pop(key)
                    else:
                        filtered[key] = value.strip()

                if "workers" in filtered and filtered["workers"] < 1:
                    filtered.pop("workers")
                if "fragments" in filtered and filtered["fragments"] < 1:
                    filtered.pop("fragments")
                if "retries" in filtered and filtered["retries"] < 0:
                    filtered.pop("retries")
                if "tui_refresh_rate" in filtered and filtered["tui_refresh_rate"] <= 0:
                    filtered.pop("tui_refresh_rate")
                for key, limit in (("workers", 32), ("fragments", 64), ("retries", 100), ("tui_refresh_rate", 12)):
                    if key in filtered:
                        filtered[key] = min(filtered[key], limit)

                if "format" in filtered:
                    filtered["format"] = str(filtered["format"]).lower()
                    if filtered["format"] not in ALLOWED_AUDIO_FORMATS:
                        filtered.pop("format")
                if "mode" in filtered:
                    filtered["mode"] = str(filtered["mode"]).lower()
                    if filtered["mode"] not in ("auto", "audio", "video"):
                        filtered.pop("mode")
                if "speed" in filtered:
                    filtered["speed"] = str(filtered["speed"]).lower()
                    if filtered["speed"] not in SPEED_PRESETS:
                        filtered.pop("speed")
                if "video_format" in filtered:
                    filtered["video_format"] = str(filtered["video_format"]).lower()
                    if filtered["video_format"] not in ALLOWED_VIDEO_FORMATS:
                        filtered.pop("video_format")
                if "video_resolution" in filtered:
                    resolution = filtered["video_resolution"].lower()
                    aliases = {"any": "", "best": "", "2160p": "4k", "4320p": "8k"}
                    resolution = aliases.get(resolution, resolution)
                    if resolution in ("", "1080p", "4k", "8k"):
                        filtered["video_resolution"] = resolution
                    else:
                        filtered.pop("video_resolution")
                if "audio_quality" in filtered:
                    aq = filtered["audio_quality"]
                    if isinstance(aq, bool) or not _valid_audio_quality(str(aq)):
                        filtered.pop("audio_quality")
                    else:
                        filtered["audio_quality"] = str(aq)
                for key in ("output_dir", "cookies_file"):
                    if key in filtered:
                        filtered[key] = os.path.expanduser(filtered[key])

                return cls(**filtered)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                Logger.warn(f"Config file corrupted, using defaults: {e}")
            except PermissionError:
                Logger.warn("Config file not readable — using defaults")
            except Exception as e:
                Logger.warn(f"Config error — using defaults: {e}")
        return defaults

    def ensure_default_output(self) -> bool:
        wanted = str(DEFAULT_OUTPUT)
        current = str(Path(self.output_dir).expanduser())
        if current in LEGACY_OUTPUTS:
            self.output_dir = wanted
            try:
                DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
                self.save()
            except Exception as e:
                Logger.warn(f"Could not save new default download folder: {e}")
            return True
        try:
            Path(self.output_dir).expanduser().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return False


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY INSTALLER
# ═══════════════════════════════════════════════════════════════════════

_dependency_install_lock = threading.RLock()


def _serialized_dependency(method):
    """Parallel jobs must not install into the same environment concurrently."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        with _dependency_install_lock:
            return method(*args, **kwargs)
    return wrapped


class DependencyInstaller:
    _cache = {}

    @staticmethod
    def _is_frozen() -> bool:
        return getattr(sys, "frozen", False)

    @classmethod
    def _ensure_local_bin_in_path(cls):
        LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)
        local = str(LOCAL_BIN_DIR)
        current = os.environ.get("PATH", "").rstrip(os.pathsep)
        if local not in current.split(os.pathsep):
            os.environ["PATH"] = local + os.pathsep + current if current else local

    @classmethod
    def _which(cls, cmd: str) -> Optional[str]:
        if cmd in cls._cache:
            cached = cls._cache[cmd]
            if cached and os.path.isfile(cached) and os.access(cached, os.X_OK):
                return cached
            cls._cache.pop(cmd, None)
        path = shutil.which(cmd)
        if path and not (os.path.isfile(path) and os.access(path, os.X_OK)):
            path = None
        cls._cache[cmd] = path
        return path

    @classmethod
    def _command_runs(cls, cmd: str, args: Optional[List[str]] = None, timeout: int = 10) -> bool:
        path = cls._which(cmd)
        if not path:
            return False
        try:
            result = subprocess.run([path] + list(args or ["--version"]),
                                    capture_output=True, text=True,
                                    stdin=subprocess.DEVNULL, timeout=timeout)
            return result.returncode == 0
        except Exception:
            cls._invalidate_cache(cmd)
            return False

    @classmethod
    def _invalidate_cache(cls, cmd: str):
        cls._cache.pop(cmd, None)

    @classmethod
    @_serialized_dependency
    def _pip_install(cls, package: str, timeout: int = 180) -> bool:
        if cls._is_frozen():
            Logger.warn(f"Cannot pip-install {package} from frozen binary")
            return False
        return cls._pip_install_in_private_venv(package, timeout=timeout)

    @classmethod
    def _venv_python(cls) -> Path:
        if sys.platform == "win32":
            return BLAZE_VENV_DIR / "Scripts" / "python.exe"
        return BLAZE_VENV_DIR / "bin" / "python"

    @classmethod
    def _add_venv_to_environment(cls):
        bin_dir = BLAZE_VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin")
        if bin_dir.is_dir():
            current = os.environ.get("PATH", "")
            if str(bin_dir) not in current.split(os.pathsep):
                os.environ["PATH"] = str(bin_dir) + os.pathsep + current
        try:
            import site
            version = f"python{sys.version_info[0]}.{sys.version_info[1]}"
            candidates = []
            if sys.platform == "win32":
                candidates.append(BLAZE_VENV_DIR / "Lib" / "site-packages")
            else:
                candidates.append(BLAZE_VENV_DIR / "lib" / version / "site-packages")
            for candidate in candidates:
                if candidate.is_dir() and str(candidate) not in sys.path:
                    site.addsitedir(str(candidate))
        except Exception:
            pass

    @classmethod
    def _pip_install_in_private_venv(cls, package: str, timeout: int = 180) -> bool:
        try:
            py = cls._venv_python()
            temporary = BLAZE_RUNTIME_DIR / "tmp"
            temporary.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            for key in ("TMPDIR", "TEMP", "TMP"):
                env[key] = str(temporary)
            env["PIP_CONFIG_FILE"] = os.devnull
            env["PYTHONNOUSERSITE"] = "1"
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            if not py.is_file():
                Logger.info("Creating Blaze private Python environment...")
                subprocess.run([sys.executable, "-m", "venv", str(BLAZE_VENV_DIR)],
                               check=True, capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=120, env=env)
            cmd = [str(py), "-m", "pip", "--isolated", "install", "--quiet", "--upgrade", "--require-virtualenv", "--no-cache-dir", "--disable-pip-version-check", package]
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=env)
            cls._add_venv_to_environment()
            Logger.success(f"{package} installed in Blaze private environment")
            return True
        except subprocess.CalledProcessError as e:
            error = (e.stderr or e.stdout or "").strip().splitlines()
            if error:
                Logger.warn(f"private environment install failed: {error[-1][:180]}")
            return False
        except Exception as e:
            Logger.warn(f"private environment install failed: {e}")
            return False

    @staticmethod
    def _refresh_user_site():
        try:
            import site
            user_site = site.getusersitepackages()
            if isinstance(user_site, str) and os.path.isdir(user_site):
                site.addsitedir(user_site)
        except Exception:
            pass

    @classmethod
    def ensure_modern_python_or_reexec(cls):
        if sys.version_info < (3, 10):
            Logger.error("Blaze requires Python 3.10+. System Python is never installed or upgraded automatically.")
            raise SystemExit(1)

    @classmethod
    def _install_via_package_manager(cls, pkg: str) -> bool:
        # Deliberately disabled: installations must stay inside Blaze.
        return False

    @classmethod
    def _install_via_package_manager_visible(cls, pkg: str) -> bool:
        return False

    @classmethod
    def _download_file(cls, url: str, dest: Path, timeout: int = 120) -> bool:
        # Publish only a complete download; retain an existing file on failure.
        temporary = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.download")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"Blaze/{VERSION}", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    Logger.warn(f"Download failed: HTTP {resp.status}")
                    return False
                expected = int(resp.headers.get("Content-Length") or 0)
                received = 0
                with open(temporary, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                if expected and received != expected:
                    Logger.warn(f"Download incomplete: {received}/{expected} bytes")
                    return False
            temporary.replace(dest)
            return True
        except Exception as e:
            Logger.warn(f"Download failed: {e}")
            return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def _is_safe_member_name(cls, name: str) -> bool:
        """Secure archive member name validation."""
        if not name:
            return False
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            return False
        parts = [p for p in normalized.split("/") if p]
        if any(p in (".", "..") for p in parts):
            return False
        return True

    @classmethod
    def _extract_binary_from_tar(cls, dl_path: Path, target_name: str, dest: Path) -> bool:
        try:
            with tarfile.open(dl_path, "r:*") as tf:
                members = tf.getmembers()
                matches = []
                for member in members:
                    norm = member.name.replace("\\", "/")
                    parts = [p for p in norm.split("/") if p]
                    if not parts or any(p in (".", "..") for p in parts):
                        continue
                    if parts[-1] != target_name:
                        continue
                    if member.issym() or member.islnk():
                        Logger.warn(f"Rejecting non-regular file member: {member.name}")
                        return False
                    if not member.isfile():
                        Logger.warn(f"Rejecting non-regular file member: {member.name}")
                        return False
                    matches.append(member)
                if len(matches) != 1:
                    Logger.warn(f"Archive did not contain exactly one safe {target_name} binary")
                    return False
                member = matches[0]
                src = tf.extractfile(member)
                if src is None:
                    Logger.warn(f"Could not read archive member: {member.name}")
                    return False
                with src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            return True
        except Exception as e:
            Logger.warn(f"Extraction failed: {e}")
            return False

    @classmethod
    def _download_and_extract(cls, url: str, target_name: str) -> bool:
        cls._ensure_local_bin_in_path()
        dl_path = LOCAL_BIN_DIR / f"_dl_{target_name}.{uuid.uuid4().hex}.tar.bz2"
        dest = LOCAL_BIN_DIR / target_name
        tmp_dest = LOCAL_BIN_DIR / f".{target_name}.{uuid.uuid4().hex}.tmp"
        try:
            Logger.info(f"Downloading {target_name}...")
            if not cls._download_file(url, dl_path):
                return False
            tmp_dest.unlink(missing_ok=True)
            if cls._extract_binary_from_tar(dl_path, target_name, tmp_dest):
                if sys.platform != "win32":
                    os.chmod(tmp_dest, 0o755)
                try:
                    result = subprocess.run([str(tmp_dest), "--version"], capture_output=True,
                                            text=True, stdin=subprocess.DEVNULL, timeout=10)
                    if result.returncode != 0:
                        Logger.warn(f"Downloaded {target_name} did not execute successfully")
                        return False
                except Exception as e:
                    Logger.warn(f"Downloaded {target_name} is unusable: {e}")
                    return False
                tmp_dest.replace(dest)
                cls._invalidate_cache(target_name)
                return cls._which(target_name) is not None
            return False
        except Exception as e:
            Logger.warn(f"Download failed for {target_name}: {e}")
            return False
        finally:
            dl_path.unlink(missing_ok=True)
            tmp_dest.unlink(missing_ok=True)

    @classmethod
    def _download_ytdlp_standalone(cls) -> Optional[str]:
        plat = sys.platform
        machine = platform.machine().lower()
        if plat == "win32":
            target = "yt-dlp.exe"
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        elif plat == "darwin":
            target = "yt-dlp_macos" if "arm" in machine else "yt-dlp_macos_legacy"
            url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{target}"
        else:
            target = "yt-dlp"
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
        dest = LOCAL_BIN_DIR / target
        tmp_dest = LOCAL_BIN_DIR / f".{target}.{uuid.uuid4().hex}.tmp"
        Logger.info("Downloading standalone yt-dlp binary...")
        try:
            if not cls._download_file(url, tmp_dest):
                return None
            if plat != "win32":
                os.chmod(tmp_dest, 0o755)
            result = subprocess.run([str(tmp_dest), "--version"], capture_output=True,
                                    text=True, stdin=subprocess.DEVNULL, timeout=10)
            if result.returncode == 0:
                tmp_dest.replace(dest)
                cls._invalidate_cache("yt-dlp")
                Logger.success("yt-dlp downloaded and verified")
                return str(dest)
            Logger.warn("Downloaded yt-dlp binary is corrupted")
        except Exception as e:
            Logger.warn(f"Downloaded yt-dlp binary is unusable: {e}")
        finally:
            try:
                tmp_dest.unlink(missing_ok=True)
            except OSError as e:
                Logger.warn(f"Cannot remove temporary yt-dlp binary: {e}")
        return None

    @classmethod
    def _ensure_ytdlp(cls) -> List[str]:
        cls._ensure_local_bin_in_path()
        if cls._command_runs("yt-dlp", ["--version"]):
            return ["yt-dlp"]
        if sys.platform == "darwin":
            # Standalone macOS downloads use release asset names, not yt-dlp.
            for name in ("yt-dlp_macos", "yt-dlp_macos_legacy"):
                stored = LOCAL_BIN_DIR / name
                if stored.is_file() and cls._command_runs(str(stored), ["--version"]):
                    return [str(stored)]
        if not cls._is_frozen():
            try:
                result = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                                        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
                if result.returncode == 0:
                    return [sys.executable, "-m", "yt_dlp"]
            except Exception:
                pass
        Logger.info("yt-dlp not found — auto-installing...")
        if cls._is_frozen():
            standalone = cls._download_ytdlp_standalone()
            if standalone:
                return [standalone]
        else:
            if cls._pip_install("yt-dlp"):
                cls._invalidate_cache("yt-dlp")
                if cls._command_runs("yt-dlp", ["--version"]):
                    Logger.success("yt-dlp installed")
                    return ["yt-dlp"]
                try:
                    result = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                                            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
                    if result.returncode == 0:
                        Logger.success("yt-dlp installed (module mode)")
                        return [sys.executable, "-m", "yt_dlp"]
                except Exception:
                    pass
                venv_python = cls._venv_python()
                if venv_python.is_file():
                    try:
                        result = subprocess.run([str(venv_python), "-m", "yt_dlp", "--version"],
                                                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
                        if result.returncode == 0:
                            Logger.success("yt-dlp installed (private environment)")
                            return [str(venv_python), "-m", "yt_dlp"]
                    except Exception:
                        pass
        Logger.error("Failed to auto-install yt-dlp.")
        Logger.info(f"Private environment: {BLAZE_VENV_DIR}. No system installation was attempted.")
        sys.exit(1)


    @classmethod
    def _ensure_ffmpeg(cls):
        cls._ensure_local_bin_in_path()
        if cls._command_runs("ffmpeg", ["-version"]):
            return
        Logger.info("ffmpeg not found — auto-installing...")
        if not cls._is_frozen():
            try:
                if cls._pip_install("imageio-ffmpeg"):
                    import imageio_ffmpeg
                    bundled = imageio_ffmpeg.get_ffmpeg_exe()
                    if bundled and Path(bundled).exists():
                        dest = LOCAL_BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
                        temporary = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.tmp")
                        try:
                            shutil.copy2(bundled, temporary)
                            if sys.platform != "win32":
                                temporary.chmod(0o755)
                            verified = subprocess.run([str(temporary), "-version"],
                                                      capture_output=True, stdin=subprocess.DEVNULL, timeout=10)
                            if verified.returncode != 0:
                                raise OSError("Bundled FFmpeg could not run")
                            temporary.replace(dest)
                        finally:
                            temporary.unlink(missing_ok=True)
                        cls._invalidate_cache("ffmpeg")
                        if cls._command_runs("ffmpeg", ["-version"]):
                            Logger.success("ffmpeg installed (bundled)")
                            return
            except Exception:
                pass
        if cls._install_via_package_manager("ffmpeg"):
            cls._invalidate_cache("ffmpeg")
            if cls._command_runs("ffmpeg", ["-version"]):
                Logger.success("ffmpeg installed via package manager")
                return
        Logger.error("Failed to auto-install ffmpeg.")
        sys.exit(1)

    @classmethod
    def _ensure_ffprobe(cls):
        if cls._command_runs("ffprobe", ["-version"]):
            return True
        Logger.info("ffprobe not found — installing ffmpeg package...")
        if cls._install_via_package_manager("ffmpeg"):
            cls._invalidate_cache("ffprobe")
            if cls._command_runs("ffprobe", ["-version"]):
                Logger.success("ffprobe installed via package manager")
                return True
        Logger.warn("ffprobe unavailable — continuing with ffmpeg/yt-dlp where possible")
        return False

    @classmethod
    def _aria2_binary_works(cls, path: Path) -> bool:
        try:
            check = subprocess.run([str(path), "--version"], capture_output=True,
                                   text=True, stdin=subprocess.DEVNULL, timeout=10)
            return (check.returncode == 0 and "aria2 version 1.37.0" in check.stdout
                    and "HTTPS" in check.stdout)
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    @_serialized_dependency
    def _ensure_aria2c(cls, private_only: bool = False) -> bool:
        cls._ensure_local_bin_in_path()
        target = "aria2c.exe" if sys.platform == "win32" else "aria2c"
        dest = LOCAL_BIN_DIR / target
        if dest.is_file() and cls._aria2_binary_works(dest):
            cls._invalidate_cache("aria2c")
            return True
        if not private_only and cls._command_runs("aria2c", ["--version"]):
            return True
        machine = platform.machine().lower()
        arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
        artifact = ARIA2_ARTIFACTS.get((sys.platform, arch))
        if artifact is None:
            Logger.warn("No private aria2c binary for this platform — using native downloading")
            return False
        url, expected_hash, is_zip = artifact
        Logger.info("Installing aria2c inside Blaze...")
        try:
            with tempfile.TemporaryDirectory(prefix="aria2-", dir=BLAZE_RUNTIME_DIR) as folder:
                staging = Path(folder)
                archive = staging / "download"
                if not cls._download_file(url, archive):
                    return False
                if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_hash:
                    Logger.warn("aria2c checksum mismatch — download was not executed")
                    return False
                candidate = staging / target
                if is_zip:
                    with zipfile.ZipFile(archive) as source:
                        entries = [entry for entry in source.infolist()
                                   if not entry.is_dir() and entry.filename.replace("\\", "/").split("/")[-1] == target]
                        if len(entries) != 1:
                            raise OSError(f"Archive must contain exactly one {target}")
                        with source.open(entries[0]) as input_file, candidate.open("wb") as output_file:
                            shutil.copyfileobj(input_file, output_file)
                else:
                    archive.replace(candidate)
                if sys.platform != "win32":
                    candidate.chmod(0o755)
                if not cls._aria2_binary_works(candidate):
                    raise OSError("aria2c did not pass its version and HTTPS capability check")
                candidate.replace(dest)
            cls._invalidate_cache("aria2c")
            Logger.success("aria2c installed in Blaze private runtime")
            return True
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            Logger.warn(f"Private aria2c installation failed: {exc}")
            return False

    @classmethod
    def ensure_all(cls, use_aria2c: bool = True) -> Tuple[List[str], bool]:
        cls._ensure_local_bin_in_path()
        ytdlp = cls._ensure_ytdlp()
        cls._ensure_ffmpeg()
        has_aria2c = cls._ensure_aria2c() if use_aria2c else False
        return ytdlp, has_aria2c

    @classmethod
    def ensure_rich(cls) -> bool:
        try:
            import rich
            return True
        except ImportError:
            pass
        Logger.info("Rich not found — auto-installing for TUI mode...")
        if not cls._pip_install("rich"):
            Logger.warn("Rich auto-install failed — falling back to standard mode")
            return False
        cls._refresh_user_site()
        try:
            import rich  # noqa: F401 -- confirm the installed module imports
            Logger.success("Rich installed")
            return True
        except ImportError:
            Logger.warn("Rich installed but could not be imported in this session")
            return False

    @classmethod
    @_serialized_dependency
    def ensure_mutagen(cls) -> bool:
        try:
            import mutagen
            return True
        except ImportError:
            pass
        Logger.info("mutagen not found — installing for thumbnail embedding...")
        if not cls._pip_install("mutagen"):
            Logger.warn("mutagen install failed — thumbnails will be skipped")
            return False
        cls._refresh_user_site()
        try:
            import mutagen  # noqa: F401 -- confirm the installed module imports
            Logger.success("mutagen installed")
            return True
        except ImportError:
            Logger.warn("mutagen installed but could not be imported")
            return False


# ═══════════════════════════════════════════════════════════════════════
# UPDATE CHECKER
# ═══════════════════════════════════════════════════════════════════════

class UpdateChecker:
    @classmethod
    def check_ytdlp(cls, ytdlp_cmd: List[str]) -> Optional[bool]:
        """True: updated; False: already current; None: failed/undetermined."""
        try:
            Logger.info("Checking for yt-dlp updates...")
            executable = shutil.which(ytdlp_cmd[0]) or ytdlp_cmd[0]
            if not Path(executable).resolve().is_relative_to(BLAZE_RUNTIME_DIR.resolve()):
                Logger.info("Installing the update privately; external yt-dlp will be left untouched")
                return True if DependencyInstaller._pip_install("yt-dlp") else None
            result = subprocess.run(list(ytdlp_cmd) + ["-U"],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
            output = result.stdout + result.stderr
            lowered = output.lower()
            if result.returncode == 0 and ("up to date" in lowered or "already up to date" in lowered):
                Logger.success("yt-dlp is up to date")
                return False
            elif result.returncode == 0 and re.search(r"\bupdated yt-dlp to\b", lowered):
                Logger.success("yt-dlp was updated to latest version")
                return True
            elif re.search(r"\bpip\b", lowered):
                Logger.info("yt-dlp is pip-managed — upgrading via pip...")
                if DependencyInstaller._pip_install("yt-dlp"):
                    Logger.success("yt-dlp upgraded via pip")
                    return True
                Logger.warn("pip upgrade failed — run: pip install -U yt-dlp")
                return None
            elif "package manager" in lowered or "homebrew" in lowered:
                Logger.warn("This external yt-dlp is package-manager managed; Blaze does not modify system packages")
                return None
            else:
                Logger.warn("Could not determine update status")
                return None
        except subprocess.TimeoutExpired:
            Logger.warn("Update check timed out")
            return None
        except Exception as e:
            Logger.warn(f"Update check failed: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════
# DOWNLOAD TRACKER
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Job:
    id: int
    url: str
    title: str = ""
    site: str = ""
    status: str = "queued"
    progress: float = 0.0
    speed: str = ""
    elapsed: float = 0.0
    error: str = ""
    mode: str = "auto"
    phase: str = "Preparing"
    eta: str = ""
    item_index: int = 0
    item_count: int = 0


class DownloadTracker:
    def __init__(self):
        self.jobs: Dict[int, Job] = {}
        self.logs: deque = deque(maxlen=100)
        self.lock = threading.RLock()
        self._counter = 0
        self.revision = 0

    def add_job(self, url: str, mode: str = "auto") -> int:
        with self.lock:
            self._counter += 1
            job = Job(id=self._counter, url=url, mode=mode)
            self.jobs[self._counter] = job
            self.revision += 1
            return self._counter

    def update_job(self, job_id: int, **kwargs):
        with self.lock:
            if job_id in self.jobs:
                for k, v in kwargs.items():
                    if k == "progress":
                        try:
                            v = float(v)
                            if not math.isfinite(v):
                                continue
                            v = max(0.0, min(100.0, v))
                        except (TypeError, ValueError, OverflowError):
                            continue
                    if k in Job.__dataclass_fields__ and k not in ("id", "url"):
                        setattr(self.jobs[job_id], k, v)
                if self.jobs[job_id].status in ("done", "failed"):
                    self.jobs[job_id].speed = ""
                    self.jobs[job_id].eta = ""
                self.revision += 1

    def add_log(self, message: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{ts}] {message}")
            self.revision += 1

    def get_stats(self) -> Tuple[int, int, int, int]:
        with self.lock:
            queued = active = done = failed = 0
            for j in self.jobs.values():
                if j.status == "queued":
                    queued += 1
                elif j.status == "downloading":
                    active += 1
                elif j.status == "done":
                    done += 1
                elif j.status == "failed":
                    failed += 1
            return queued, active, done, failed

    def all_terminal(self) -> bool:
        with self.lock:
            return len(self.jobs) > 0 and all(j.status in ("done", "failed") for j in self.jobs.values())


# ═══════════════════════════════════════════════════════════════════════
# MODE DETECTION
# ═══════════════════════════════════════════════════════════════════════

class ModeDetector:
    @staticmethod
    def extract_site(url: str) -> str:
        try:
            from urllib.parse import urlparse
            netloc = (urlparse(url).hostname or "").lower()
            return netloc[4:] if netloc.startswith("www.") else netloc
        except Exception:
            return "unknown"

    @classmethod
    def detect_mode(cls, url: str) -> str:
        site = cls.extract_site(url)
        # Direct media links may contain signed query strings or encoded names.
        from urllib.parse import urlparse, unquote
        try:
            suffix = Path(unquote(urlparse(url).path)).suffix.lower()
        except ValueError:
            suffix = ""
        if suffix in AUDIO_EXTENSIONS:
            return "audio"
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        # Check audio-only hosts
        for host in AUDIO_ONLY_HOSTS:
            if site == host or site.endswith("." + host):
                return "audio"
        # Check video hosts
        for host in VIDEO_HOSTS:
            if site == host or site.endswith("." + host):
                return "video"
        # Fallback
        return "video"


def output_dir_for_mode(base_dir: Path, mode: str) -> Path:
    base_dir = Path(base_dir).expanduser()
    if mode == "audio":
        return base_dir / "Audio"
    if mode == "video":
        return base_dir / "Video"
    return base_dir


def is_spotify_url(url: str) -> bool:
    site = ModeDetector.extract_site(url)
    return site == "spotify.com" or site.endswith(".spotify.com")


def validate_download_url(url: str) -> str:
    from urllib.parse import urlparse
    url = url.strip()
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise ValueError("URL contains whitespace or control characters")
    try:
        parsed = urlparse(url)
        _ = parsed.port  # Reject invalid/out-of-range ports before installing anything.
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username is not None:
            raise ValueError("Enter a valid HTTP or HTTPS URL without embedded credentials")
    except ValueError as exc:
        raise ValueError(f"Invalid download URL: {exc}") from exc
    if is_spotify_url(url):
        raise ValueError("Spotify links are not supported. Use the original audio or video source URL.")
    return url


def should_auto_use_safari_cookies(url: str, config: Config) -> bool:
    if config.cookies_browser or config.cookies_file:
        return False
    site = ModeDetector.extract_site(url)
    return sys.platform == "darwin" and (site == "instagram.com" or site.endswith(".instagram.com"))


# ═══════════════════════════════════════════════════════════════════════
# DOWNLOAD ENGINE
# ═══════════════════════════════════════════════════════════════════════

_shutdown_requested = False
_active_processes: set = set()
_process_lock = threading.Lock()


@contextmanager
def _destination_lock(root: Path, mode: str):
    """Serialize writes to one media folder, including separate Blaze processes.

    Extractor aliases and overlapping playlists can resolve to the same files.
    Fragment downloads remain parallel.
    The OS releases this lock even if Blaze crashes; never unlink the lock file.
    """
    state = root / ".blaze"
    state.mkdir(parents=True, exist_ok=True)
    with (state / f"{mode}.lock").open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
            handle.flush()
        acquired = False
        notified = False
        try:
            while not acquired:
                if _shutdown_requested:
                    raise InterruptedError("interrupted while waiting for the output folder")
                try:
                    if sys.platform == "win32":
                        import msvcrt
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if not notified:
                        Logger.info(f"Waiting for another download writing to {output_dir_for_mode(root, mode)}")
                        notified = True
                    time.sleep(0.1)
            yield
        finally:
            if acquired:
                if sys.platform == "win32":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _register_process(process: subprocess.Popen):
    with _process_lock:
        _active_processes.add(process)


def _unregister_process(process: subprocess.Popen):
    with _process_lock:
        _active_processes.discard(process)


def _kill_all_active_processes():
    with _process_lock:
        procs = list(_active_processes)
    for proc in procs:
        DownloadEngine._kill_process_tree(proc)


def _iter_progress_lines(stream, chunk_size: int = 128):
    """Yield output lines split on both \n and \r. Reads in chunks to minimize CPU."""
    buf = ""
    while True:
        try:
            chunk = stream.read(chunk_size)
        except Exception:
            break
        if not chunk:
            if buf.strip():
                yield buf
            return
        buf += chunk
        while "\r" in buf or "\n" in buf:
            r_idx = buf.find("\r")
            n_idx = buf.find("\n")
            if r_idx != -1 and n_idx != -1:
                idx = min(r_idx, n_idx)
            else:
                idx = r_idx if r_idx != -1 else n_idx
            line = buf[:idx]
            buf = buf[idx + 1:]
            if line.strip():
                yield line


class DownloadEngine:
    def __init__(self, ytdlp_cmd, config, has_aria2c, tracker=None, speed="fast"):
        if isinstance(ytdlp_cmd, str):
            self.ytdlp_cmd = [ytdlp_cmd]
        else:
            self.ytdlp_cmd = list(ytdlp_cmd)
        self.config = config
        self.has_aria2c = has_aria2c
        self.tracker = tracker
        self.speed = speed
        DownloadEngine._setup_signal_handler()

    @classmethod
    def _setup_signal_handler(cls):
        if threading.current_thread() is not threading.main_thread():
            return
        if getattr(cls, "_signal_installed", False):
            return
        cls._signal_installed = True

        def _safe_stderr_write(msg: bytes):
            try:
                os.write(sys.stderr.fileno(), msg)
            except (OSError, ValueError, AttributeError):
                pass

        def handler(signum, frame):
            global _shutdown_requested
            if _shutdown_requested:
                _safe_stderr_write(b"\nForce exit\n")
                _kill_all_active_processes()
                os._exit(130)
            _shutdown_requested = True
            _safe_stderr_write(b"\nInterrupted. Stopping downloads; partial files are kept...\n")
            # Wake input()/Rich prompts as well as download polling loops.
            raise KeyboardInterrupt
        signal.signal(signal.SIGINT, handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handler)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, handler)

    @staticmethod
    def _kill_process_tree(process: subprocess.Popen):
        _unregister_process(process)
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                               capture_output=True, timeout=5)
            else:
                # Children are started in a new session: save the group ID before
                # reaping its leader, or ffmpeg/aria2c may survive cancellation.
                pgid = process.pid
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass

    def _get_speed_config(self) -> Dict:
        return SPEED_CONFIG.get(self.speed, SPEED_CONFIG["fast"])

    def _dashboard_flags(self) -> List[str]:
        if self.tracker is None:
            return []
        return ["--progress", "--progress-delta", "0.1",
                "--progress-template", "download:BLAZE_PROGRESS:%(progress)j",
                "--print", "before_dl:BLAZE_MEDIA:%(.{title,id,playlist_index,playlist_count})j"]

    def _build_audio_output_template(self, output_dir: Path, playlist: bool = False) -> str:
        base = str(output_dir).replace("%", "%%")
        ext = "%(ext)s"
        # Keep default filenames compatible, but do not mistake another quality
        # profile's existing file for a completed download.
        quality = float(self.config.audio_quality)
        quality_label = str(int(quality)) if quality.is_integer() else str(quality)
        suffix = f" - q{quality_label}" if quality else ""
        if playlist:
            subdir = "%(playlist_title)s" if self.config.create_subdirs else ""
            template = "%(playlist_index)03d - %(title).80s [%(id)s]" + suffix + "." + ext
            if subdir:
                return os.path.join(base, subdir, template)
            return os.path.join(base, template)
        return os.path.join(base, "%(title).100s [%(id)s]" + suffix + "." + ext)

    def _build_video_output_template(self, output_dir: Path, playlist: bool = False, vformat: str = "mp4") -> str:
        base = str(output_dir).replace("%", "%%")
        ext = "%(ext)s"
        suffix = " - " + (self.config.video_resolution or "best") + " - " + vformat
        if playlist:
            subdir = "%(playlist_title)s" if self.config.create_subdirs else ""
            template = "%(playlist_index)03d - %(title).80s [%(id)s]" + suffix + "." + ext
            if subdir:
                return os.path.join(base, subdir, template)
            return os.path.join(base, template)
        return os.path.join(base, "%(title).100s [%(id)s]" + suffix + "." + ext)

    def _download_archive_path(self, mode: str) -> Path:
        root = getattr(self, "_archive_root", Path(self.config.output_dir).expanduser())
        profile = (self.config.format + "-" + self.config.audio_quality if mode == "audio"
                   else self.config.video_format + "-" + (self.config.video_resolution or "best"))
        state = root / ".blaze"
        state.mkdir(parents=True, exist_ok=True)
        return state / f"{mode}-{profile}-archive.txt"

    def _history_flags(self, mode: str) -> List[str]:
        """Repair recorded missing files while holding the destination lock.

        yt-dlp appends final paths after postprocessing, before adding archive
        entries. Thus interrupted conversions never become verified completions.
        Preserve untracked legacy entries; --ignore-history can recover those.
        """
        archive = self._download_archive_path(mode)
        records = archive.with_suffix(".files.jsonl")
        if records.is_file() and records.stat().st_size:
            # Keep new records separate from any truncated line left by a crash.
            with records.open("rb+") as stream:
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    stream.write(b"\n")
        if archive.is_file() and records.is_file():
            known = {}
            with records.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                        extractor, identity, filename = (item[k] for k in ("extractor_key", "id", "filepath"))
                        if not all(isinstance(v, str) and v for v in (extractor, identity, filename)):
                            continue
                        path = Path(filename)
                        if not path.is_absolute():
                            continue
                        key = f"{extractor.lower()} {identity}"
                        known[key] = known.get(key, False) or path.is_file()
                    except (ValueError, KeyError, TypeError):
                        # A crash may leave a partial final line; do not guess.
                        continue
            missing = {key for key, exists in known.items() if not exists}
            if missing:
                original = archive.read_text(encoding="utf-8")
                lines = original.splitlines(keepends=True)
                kept = [line for line in lines if line.strip() not in missing]
                if len(kept) != len(lines):
                    temporary = archive.with_name(f".{archive.name}.{uuid.uuid4().hex}.tmp")
                    try:
                        temporary.write_text("".join(kept), encoding="utf-8")
                        temporary.replace(archive)
                    finally:
                        temporary.unlink(missing_ok=True)
                    Logger.info(f"Retrying {len(lines) - len(kept)} missing file(s) from download history")
        flags = ["--print-to-file", "after_move:%(.{id,extractor_key,filepath})j",
                 str(records).replace("%", "%%")]
        if not self.config.ignore_history:
            flags += ["--download-archive", str(archive)]
        return flags

    def _build_audio_flags(self, playlist: bool = False, show_progress: bool = True) -> List[str]:
        fmt = self.config.format.lower()
        sc = self._get_speed_config()

        flags = []
        # For audio we extract audio
        flags.append("--extract-audio")
        flags.append("--audio-format")

        # OGG maps to vorbis
        if fmt == "ogg":
            flags.append("vorbis")
        else:
            flags.append(fmt)

        flags += ["--audio-quality", self.config.audio_quality]
        flags += ["--format", "ba/b"]
        flags += ["--concurrent-fragments", str(max(1, self.config.fragments))]
        flags += ["--buffer-size", "16K"]
        flags += ["--http-chunk-size", "10M"]
        flags += ["--newline", "--ignore-config", "--no-abort-on-error",
                  "--abort-on-unavailable-fragments", "--socket-timeout", "30",
                  "--retry-sleep", "exp=1:20", "--no-simulate"]

        if self.config.insecure:
            flags.append("--no-check-certificates")

        if show_progress and not Logger.QUIET:
            flags.append("--progress")

        if Logger.QUIET:
            flags.append("--quiet")

        flags += ["--continue", "--no-overwrites"]
        flags += self._history_flags("audio")
        flags += ["--retries", str(self.config.retries)]
        flags += ["--fragment-retries", str(self.config.retries)]

        if self.config.write_metadata:
            flags += ["--embed-metadata"]

        # Thumbnail handling: WAV must not embed; others may if deps available
        thumbnail_safe = False
        if fmt == "wav":
            flags += ["--no-write-thumbnail"]
        else:
            if fmt in ("mp3", "m4a", "flac"):
                thumbnail_safe = True

        if thumbnail_safe and self.config.write_thumbnails:
            if DependencyInstaller._command_runs("ffmpeg", ["-version"]) and DependencyInstaller.ensure_mutagen():
                flags += ["--embed-thumbnail"]
            else:
                flags += ["--no-write-thumbnail"]
        elif not self.config.write_thumbnails:
            flags += ["--no-write-thumbnail"]

        if not playlist:
            flags += ["--no-playlist"]

        ffmpeg_path = DependencyInstaller._which("ffmpeg")
        if ffmpeg_path:
            flags += ["--ffmpeg-location", ffmpeg_path]

        # yt-dlp groups both HTTP and HTTPS under the "http" selector.
        if self.config.use_aria2c and self.has_aria2c:
            flags += ["--downloader", "http,ftp:aria2c"]
            flags += ["--downloader-args",
                      f"aria2c:-x {sc['aria_connections']} -s {sc['aria_segments']} -k 1M -c --file-allocation=none --optimize-concurrent-downloads=true"]

        # Cookies/auth
        if self.config.cookies_file:
            flags += ["--cookies", self.config.cookies_file]
        if self.config.cookies_browser:
            flags += ["--cookies-from-browser", self.config.cookies_browser]

        return flags + self._dashboard_flags()

    def _build_video_flags(self, playlist: bool = False, show_progress: bool = True,
                           resolution: str = "", output_format: str = "mp4") -> List[str]:
        sc = self._get_speed_config()
        flags = []

        # Must NOT use --extract-audio in video mode
        fmt_selector = "bv*+ba/b"
        if resolution == "1080p":
            fmt_selector = "bv*[height<=1080]+ba/b[height<=1080]"
        elif resolution == "4k" or resolution == "2160p":
            fmt_selector = "bv*[height<=2160]+ba/b[height<=2160]"
        elif resolution == "8k" or resolution == "4320p":
            fmt_selector = "bv*[height<=4320]+ba/b[height<=4320]"

        flags += ["--format", fmt_selector]
        flags += ["--concurrent-fragments", str(max(1, self.config.fragments))]
        flags += ["--buffer-size", "16K"]
        flags += ["--http-chunk-size", "10M"]
        flags += ["--newline", "--ignore-config", "--no-abort-on-error",
                  "--abort-on-unavailable-fragments", "--socket-timeout", "30",
                  "--retry-sleep", "exp=1:20", "--no-simulate"]

        if self.config.insecure:
            flags.append("--no-check-certificates")

        if show_progress and not Logger.QUIET:
            flags.append("--progress")

        if Logger.QUIET:
            flags.append("--quiet")

        flags += ["--continue", "--no-overwrites"]
        flags += self._history_flags("video")
        flags += ["--retries", str(self.config.retries)]
        flags += ["--fragment-retries", str(self.config.retries)]

        if self.config.write_metadata:
            flags += ["--embed-metadata"]

        # Thumbnail option where safe for video
        if self.config.write_thumbnails:
            if DependencyInstaller._command_runs("ffmpeg", ["-version"]) and DependencyInstaller.ensure_mutagen():
                flags += ["--embed-thumbnail"]
            else:
                flags += ["--no-write-thumbnail"]
        else:
            flags += ["--no-write-thumbnail"]

        # Subtitles option
        if self.config.write_subtitles:
            flags += ["--write-subs", "--sub-langs", "en"]

        # Merge video/audio with ffmpeg, unless the user asked yt-dlp to keep its best container.
        if output_format == "best":
            pass
        elif output_format == "mkv":
            flags += ["--merge-output-format", "mkv", "--remux-video", "mkv"]
        else:
            flags += ["--merge-output-format", "mp4", "--remux-video", "mp4"]

        if not playlist:
            flags += ["--no-playlist"]

        ffmpeg_path = DependencyInstaller._which("ffmpeg")
        if ffmpeg_path:
            flags += ["--ffmpeg-location", ffmpeg_path]

        # yt-dlp groups both HTTP and HTTPS under the "http" selector.
        if self.config.use_aria2c and self.has_aria2c:
            flags += ["--downloader", "http,ftp:aria2c"]
            flags += ["--downloader-args",
                      f"aria2c:-x {sc['aria_connections']} -s {sc['aria_segments']} -k 1M -c --file-allocation=none --optimize-concurrent-downloads=true"]

        # Cookies/auth
        if self.config.cookies_file:
            flags += ["--cookies", self.config.cookies_file]
        if self.config.cookies_browser:
            flags += ["--cookies-from-browser", self.config.cookies_browser]

        return flags + self._dashboard_flags()

    def _extract_site(self, url: str) -> str:
        return ModeDetector.extract_site(url)

    def _parse_ytdlp_line(self, line: str, job_id: int, tracker):
        if not tracker:
            return
        line = line.strip()
        if not line:
            return

        if line.startswith("BLAZE_MEDIA:"):
            try:
                item = json.loads(line.partition(":")[2])
                if not isinstance(item, dict):
                    return
                def item_number(name):
                    value = item.get(name)
                    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
                title = item.get("title") or item.get("id")
                if not isinstance(title, str):
                    title = ""
                tracker.update_job(job_id, title=title, progress=0.0, phase="Preparing", speed="", eta="",
                                   item_index=item_number("playlist_index"), item_count=item_number("playlist_count"))
            except (ValueError, TypeError):
                pass
            return
        if line.startswith("BLAZE_PROGRESS:"):
            try:
                progress = json.loads(line.partition(":")[2])
                if not isinstance(progress, dict):
                    return
                status = progress.get("status")
                if status not in ("downloading", "finished"):
                    return
                def number(name):
                    value = progress.get(name)
                    if isinstance(value, bool):
                        return 0.0
                    value = float(value or 0)
                    return value if math.isfinite(value) and value >= 0 else 0.0
                total = number("total_bytes") or number("total_bytes_estimate")
                downloaded = number("downloaded_bytes")
                rate = number("speed")
                eta = number("eta")
                eta_text = f"{int(eta) // 60:02}:{int(eta) % 60:02}" if eta else ""
                scale, unit = (1024 ** 3, "GiB/s") if rate >= 1024 ** 3 else (1024 ** 2, "MiB/s") if rate >= 1024 ** 2 else (1024, "KiB/s") if rate >= 1024 else (1, "B/s")
                values = dict(phase="Finishing" if status == "finished" else "Downloading",
                              speed=f"{rate / scale:.1f} {unit}" if rate and status == "downloading" else "",
                              eta=eta_text if status == "downloading" else "")
                if status == "finished" or total:
                    values["progress"] = 100.0 if status == "finished" else 100 * downloaded / total
                tracker.update_job(job_id, **values)
            except (ValueError, TypeError, OverflowError):
                pass
            return

        phase_match = re.match(r"^\[(ExtractAudio|Merger|VideoRemuxer|VideoConvertor|EmbedThumbnail|EmbedSubtitle|Metadata|Fixup\w*)\]", line)
        if phase_match:
            stage = phase_match.group(1)
            phase = ("Converting" if stage == "ExtractAudio" or stage == "VideoConvertor"
                     else "Merging" if stage == "Merger" else "Finishing")
            tracker.update_job(job_id, phase=phase, eta="", speed="")
        elif line.startswith("[download]") and "%" in line:
            eta_match = re.search(r"\bETA\s+([0-9:]+)", line)
            tracker.update_job(job_id, phase="Downloading",
                               eta=eta_match.group(1) if eta_match else "")

        # Structured titles keep their Unicode text throughout postprocessing.
        with tracker.lock:
            has_title = bool(tracker.jobs.get(job_id) and tracker.jobs[job_id].title)
        if not has_title and "[info]" in line and "Downloading" in line:
            try:
                m = re.match(r"\[info\]\s+(.+?):\s*Downloading", line)
                if m:
                    title = m.group(1).strip()
                    if title and len(title) > 2:
                        tracker.update_job(job_id, title=title)
            except Exception:
                pass

        if not has_title and "Destination:" in line:
            try:
                dest = line.split("Destination:")[-1].strip()
                fname = os.path.basename(dest)
                title = fname.rsplit(".", 1)[0].rsplit(" [", 1)[0]
                if title and len(title) > 2:
                    tracker.update_job(job_id, title=title)
            except Exception:
                pass

        # Progress parsing
        if line.startswith("[download]") and "%" in line and " of " in line:
            try:
                pct_str = line.split("%")[0].split()[-1]
                pct = float(pct_str)
                tracker.update_job(job_id, progress=pct)
            except (ValueError, IndexError):
                pass

        m = re.search(r"\((\d+(?:\.\d+)?)%\)", line)
        if m:
            try:
                tracker.update_job(job_id, progress=float(m.group(1)))
            except (ValueError, IndexError):
                pass

        m = re.search(r"DL:(\d+(?:\.\d+)?)([KMG]i?B)", line)
        if m:
            tracker.update_job(job_id, speed=m.group(1) + m.group(2) + "/s")

        if "MiB/s" in line or "KiB/s" in line or "B/s" in line:
            try:
                m = re.search(r"(\d+(?:\.\d+)?\s*(?:KiB|MiB|GiB|B)/s)", line)
                if m:
                    tracker.update_job(job_id, speed=m.group(1))
            except Exception:
                pass

        lower = line.lower()
        if lower.startswith("error:"):
            tracker.add_log(f"error: {line[:80]}")
        elif lower.startswith("warning:"):
            tracker.add_log(f"warn: {line[:80]}")




    def _run_command(self, cmd, job_id=None):
        """Read pipes on a daemon thread so silent children remain cancellable."""
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                      errors="replace", bufsize=1)
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        messages = queue.Queue(maxsize=1024)
        process = subprocess.Popen(cmd, **kwargs)
        _register_process(process)
        stopped = threading.Event()
        self._last_lines = deque(maxlen=300)
        self._saw_error = False
        self._last_error = ""
        reader_errors = []

        def read_output():
            try:
                for line in process.stdout:
                    while not stopped.is_set():
                        try:
                            messages.put(line, timeout=0.1)
                            break
                        except queue.Full:
                            pass
                    if stopped.is_set():
                        break
            except Exception as exc:
                reader_errors.append(str(exc))
            finally:
                process.stdout.close()

        reader = threading.Thread(target=read_output, daemon=True)
        try:
            reader.start()
            with self._report_path.with_suffix(".log").open("a", encoding="utf-8") as log:
                log.write("\n--- Downloader attempt ---\n")
                while reader.is_alive() or not messages.empty() or process.poll() is None:
                    if _shutdown_requested:
                        self._kill_process_tree(process)
                        return 130
                    if reader_errors:
                        self._last_error = f"Cannot read downloader output: {reader_errors[0]}"
                        self._kill_process_tree(process)
                        return 1
                    try:
                        line = messages.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    log.write(line)
                    log.flush()
                    clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
                    self._last_lines.append(clean)
                    # Match diagnostics, not words inside a media title/path.
                    if re.match(r"(?i)^(?:ERROR(?:\s*\[[^\]]+\])?\s*:|\w+(?:Error|Exception):|(?:no results found|could not find|failed to download)\b)", clean):
                        self._saw_error = True
                        self._last_error = clean
                    if self.tracker and job_id:
                        self._parse_ytdlp_line(clean, job_id, self.tracker)
                    elif not Logger.QUIET:
                        print(clean, flush=True)
                code = process.wait()
                if reader_errors:
                    self._last_error = f"Cannot read downloader output: {reader_errors[0]}"
                    return code or 1
                return code or (1 if self._saw_error else 0)
        finally:
            stopped.set()
            if process.poll() is None:
                self._kill_process_tree(process)
            if reader.ident is not None:
                reader.join(timeout=2)
            else:
                process.stdout.close()
            _unregister_process(process)

    def download(self, url, output_dir, mode="auto", playlist=False, job_id=None,
                 show_progress=True, print_debug=False, retry_with_update=False,
                 _retry_done=False):
        worker = object.__new__(DownloadEngine)
        worker.__dict__ = self.__dict__.copy()
        worker.config = replace(self.config)
        worker._archive_root = Path(output_dir).expanduser().resolve()
        started = datetime.now().astimezone().isoformat()
        success = False
        error = ""
        worker._report_path = None
        worker._last_error = ""
        worker._exit_code = None
        try:
            url = validate_download_url(url)
            reports = worker._archive_root / "Reports"
            reports.mkdir(parents=True, exist_ok=True)
            worker._report_path = reports / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:10] + ".json")
            target_mode = mode if mode in ("audio", "video") else ModeDetector.detect_mode(url)
            worker._effective_mode = target_mode
            if self.tracker and job_id:
                self.tracker.update_job(job_id, mode=target_mode, phase="Waiting")
            with _destination_lock(worker._archive_root, target_mode):
                success = worker._download_impl(url, worker._archive_root, mode, playlist, job_id,
                                                show_progress, print_debug, retry_with_update, _retry_done)
            if not success:
                error = worker._last_error or ("interrupted" if _shutdown_requested else "Download failed; see job log")
            return success
        except (Exception, SystemExit) as exc:
            error = str(exc)
            if not Logger.QUIET:
                Logger.error(error)
            return False
        finally:
            if not success and _shutdown_requested:
                error = error or "interrupted"
            if not success and Logger.QUIET:
                Logger.error(error or f"Download failed; report: {worker._report_path}")
            if not success and self.tracker and job_id:
                with self.tracker.lock:
                    job = self.tracker.jobs.get(job_id)
                    detail = (job.error if job else "") or error or ("interrupted" if _shutdown_requested else "see job log")
                    self.tracker.update_job(job_id, status="failed", error=detail)
            if worker._report_path:
                report = dict(url=url, started=started, finished=datetime.now().astimezone().isoformat(),
                              status="interrupted" if _shutdown_requested else ("succeeded" if success else "failed"),
                              mode=getattr(worker, "_effective_mode", mode), audio_format=worker.config.format,
                              video_format=worker.config.video_format, video_resolution=worker.config.video_resolution,
                              error=error, exit_code=worker._exit_code,
                              playlist=playlist, log=str(worker._report_path.with_suffix(".log")),
                              scope="URL job result; not an independent per-track completeness audit")
                try:
                    worker._report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                except OSError as exc:
                    Logger.error(f"Could not write job report: {exc}")

    def _download_impl(self, url: str, output_dir: Path, mode: str = "auto",
                 playlist: bool = False, job_id=None, show_progress: bool = True,
                 print_debug: bool = False, retry_with_update: bool = False,
                 _retry_done: bool = False) -> bool:
        """Download a single URL. Returns True on success."""
        tracker = self.tracker
        if _shutdown_requested:
            if tracker and job_id:
                tracker.update_job(job_id, status="failed", error="interrupted")
            return False

        output_dir = Path(output_dir).expanduser()
        base_output_dir = output_dir
        effective_mode = mode if mode in ("audio", "video") else ModeDetector.detect_mode(url)
        self._effective_mode = effective_mode
        output_dir = output_dir_for_mode(output_dir, effective_mode)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            Logger.error(f"Cannot create output directory: {e}")
            if tracker and job_id:
                tracker.update_job(job_id, status="failed", error=f"bad output dir: {e}")
            return False

        site = self._extract_site(url)
        original_cookie_browser = self.config.cookies_browser
        if should_auto_use_safari_cookies(url, self.config):
            self.config.cookies_browser = "safari"

        if tracker and job_id:
            tracker.update_job(job_id, site=site, mode=effective_mode, status="downloading", phase="Preparing", progress=0, error="", eta="", speed="")
            tracker.add_log(f"started ({effective_mode}): {url[:60]}...")

        try:
            # Build flags based on mode
            if effective_mode == "audio":
                flags = self._build_audio_flags(playlist, show_progress)
                template = self._build_audio_output_template(output_dir, playlist)
            else:
                vformat = self.config.video_format
                resolution = self.config.video_resolution
                flags = self._build_video_flags(playlist, show_progress, resolution, vformat)
                template = self._build_video_output_template(output_dir, playlist, vformat)

            cmd = list(self.ytdlp_cmd) + flags + ["--output", template, "--", url]

            if print_debug or Logger.QUIET:
                # Safely print the command
                cmd_str = " ".join(shlex.quote(c) for c in cmd)
                Logger.info(f"Command: {cmd_str}")

            start = time.monotonic()
            result_code = self._run_command(cmd, job_id)
            self._exit_code = result_code

            elapsed = time.monotonic() - start

            if result_code == 0:
                if tracker and job_id:
                    tracker.update_job(job_id, status="done", progress=100.0, elapsed=elapsed)
                    tracker.add_log(f"completed in {elapsed:.1f}s: {url[:60]}...")
                elif not Logger.QUIET:
                    Logger.success(f"Completed in {elapsed:.1f}s")
                return True

            else:
                self._last_error = self._last_error or f"Downloader exited with code {result_code}"
                # Retry with update on extractor failure
                if retry_with_update and not _retry_done and not _shutdown_requested:
                    Logger.info("Extractor failure — running yt-dlp update and retrying...")
                    UpdateChecker.check_ytdlp(self.ytdlp_cmd)
                    refreshed = DependencyInstaller._ensure_ytdlp()
                    if refreshed:
                        self.ytdlp_cmd = refreshed
                    Logger.info("Retrying download...")
                    return self._download_impl(url, base_output_dir, mode, playlist, job_id, show_progress, print_debug, retry_with_update, _retry_done=True)

                if tracker and job_id:
                    tracker.update_job(job_id, status="failed", error=self._last_error)
                    tracker.add_log(f"failed (code {result_code}): {url[:60]}...")
                elif not Logger.QUIET:
                    Logger.error(f"Failed (exit code {result_code})")
                return False

        except Exception as e:
            self._last_error = str(e)
            if tracker and job_id:
                tracker.update_job(job_id, status="failed", error=str(e))
                tracker.add_log(f"exception: {str(e)[:60]}")
            elif not Logger.QUIET:
                Logger.error(f"Exception: {e}")
            return False
        finally:
            self.config.cookies_browser = original_cookie_browser

    def batch_parallel(self, urls: List[str], output_dir: Path, max_workers: int, mode: str = "auto",
                       playlist: bool = False, pre_allocated_jobs=None,
                       print_debug: bool = False, retry_with_update: bool = False) -> Tuple[int, int]:
        urls = list(dict.fromkeys(urls))
        if not urls:
            return 0, 0
        output_dir = Path(output_dir).expanduser()
        total = len(urls)
        max_workers = max(1, min(max_workers, total))
        tracker = self.tracker
        if not tracker and not Logger.QUIET:
            print(f"\n{Style.BOLD}{Style.CYAN}⚡ Parallel Batch Mode{Style.RESET}")
            print(f"{Style.DIM}URLs:{Style.RESET} {total}  {Style.DIM}Workers:{Style.RESET} {max_workers}  {Style.DIM}Output:{Style.RESET} {output_dir}\n")
        completed = 0
        failed = 0
        show_progress = tracker is not None
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        futures = {}
        try:
            for url in urls:
                if _shutdown_requested:
                    break
                job_id = None
                if tracker:
                    if pre_allocated_jobs and url in pre_allocated_jobs:
                        job_id = pre_allocated_jobs[url]
                    else:
                        job_id = tracker.add_job(url, mode=mode)
                url_mode = ModeDetector.detect_mode(url) if mode == "auto" else mode
                future = executor.submit(self.download, url, output_dir, url_mode, playlist, job_id, show_progress, print_debug, retry_with_update)
                futures[future] = url
            for future in concurrent.futures.as_completed(futures):
                if _shutdown_requested:
                    break
                url = futures[future]
                if future.cancelled():
                    failed += 1
                    continue
                try:
                    if future.result():
                        completed += 1
                    else:
                        failed += 1
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    Logger.error(f"{url}: {e}")
                    failed += 1
                if not tracker and not Logger.QUIET:
                    print(f"{Style.DIM}[{completed}/{total} completed, {failed} failed]{Style.RESET}")
        finally:
            if _shutdown_requested:
                _kill_all_active_processes()
            for future in futures:
                future.cancel()
            # Finish cancellation and report writes before returning to the UI.
            executor.shutdown(wait=True, cancel_futures=True)
            if tracker:
                with tracker.lock:
                    for job in tracker.jobs.values():
                        if job.status == "queued":
                            tracker.update_job(job.id, status="failed", error="never started")
        if not self.tracker and not Logger.QUIET:
            print(f"\n{Style.GREEN}{Style.BOLD}+ Batch complete:{Style.RESET} {completed} succeeded, {failed} failed")
        return completed, max(failed, total - completed)


# ═══════════════════════════════════════════════════════════════════════
# RICH TUI MODE
# ═══════════════════════════════════════════════════════════════════════

@contextmanager
def dashboard_keys():
    """Nonblocking keys with terminal settings restored before the next prompt."""
    saved = None
    fd = None
    def none():
        return ""
    poll = none
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            if sys.platform == "win32":
                import msvcrt
                def poll():
                    if not msvcrt.kbhit():
                        return ""
                    key = msvcrt.getwch()
                    if key in ("\x00", "\xe0"):
                        if msvcrt.kbhit():
                            msvcrt.getwch()
                        return ""
                    return key.lower()
            else:
                import select
                import termios
                import tty
                fd = sys.stdin.fileno()
                saved = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                def poll():
                    if select.select([fd], [], [], 0)[0]:
                        key = os.read(fd, 1).decode("utf-8", errors="ignore").lower()
                        if key == "\x1b":
                            while select.select([fd], [], [], 0)[0]:
                                os.read(fd, 16)
                            return ""
                        return key
                    return ""
    except (OSError, ValueError, AttributeError, ImportError):
        poll = none
    try:
        yield poll
    finally:
        if saved is not None and fd is not None:
            try:
                import termios
                termios.tcsetattr(fd, termios.TCSADRAIN, saved)
            except (OSError, ValueError):
                pass


def terminal_text(value) -> str:
    """Keep untrusted titles/diagnostics literal and on one safe terminal line."""
    value = str(value)
    value = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", value)
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def dashboard_page_size(width: int, height: int) -> int:
    if height < 12 or width < 24:
        return max(1, height - 3)
    return max(1, height - (12 if height < 20 else 17))


def dashboard_selected_jobs(jobs, view: str):
    if view == "failed":
        jobs = [job for job in jobs if job.status == "failed"]
    elif view == "active":
        jobs = [job for job in jobs if job.status in ("queued", "downloading")]
    return sorted(jobs, key=lambda job: job.id)


def build_terminal_dashboard(tracker: DownloadTracker, config: Config, output_dir: Path,
                             mode: str, has_aria2c: bool, width: int, height: int,
                             elapsed_seconds: float = 0.0, page: int = 0, view: str = "all"):
    """Stable rows, smooth progress and an exact height budget at any terminal size."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    width, height = max(1, int(width)), max(1, int(height))
    with tracker.lock:
        jobs = [replace(job) for job in tracker.jobs.values()]
        logs = list(tracker.logs)
    counts = {status: sum(job.status == status for job in jobs)
              for status in ("queued", "downloading", "done", "failed")}
    elapsed = max(0, int(elapsed_seconds))
    clock = f"{elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}"
    settled = counts["done"] + counts["failed"]
    selected = dashboard_selected_jobs(jobs, view)
    row_limit = dashboard_page_size(width, height)
    pages = max(1, (len(selected) + row_limit - 1) // row_limit)
    page %= pages
    visible = selected[page * row_limit:(page + 1) * row_limit]
    empty = "No failed downloads" if view == "failed" else "No active downloads" if view == "active" else "Queue is empty"
    # Very small windows remain usable, rather than letting Rich crop the footer.
    if height < 12 or width < 24:
        lines = [f"BLAZE {clock} | {settled}/{len(jobs)}"]
        pagination = [f"Page {page + 1}/{pages} | N/P"] if pages > 1 and height > 2 else []
        available = max(0, height - 2 - len(pagination))
        for job in visible[:available]:
            stage = job.phase if job.status == "downloading" else job.status.title()
            lines.append(f"#{job.id} {terminal_text(job.title or job.url)} | {stage}")
        if not visible and available:
            lines.append(empty)
        lines.extend(pagination)
        if height > 1:
            lines.append("Q stop | A all | F failed")
        cropped = []
        for line in lines:
            text = Text(line, no_wrap=True, overflow="ellipsis")
            text.truncate(width, overflow="ellipsis")
            cropped.append(text)
        return Group(*cropped)

    header = Text(f"BLAZE  •  {mode.upper()}  •  {clock}\n", style="bold cyan", no_wrap=True, overflow="ellipsis")
    for label, status, style in (("Queued", "queued", "dim"), ("Active", "downloading", "cyan"),
                                  ("Done", "done", "green"), ("Failed", "failed", "red")):
        header.append(f"{label} {counts[status]}  ", style=style)
    header.append(f"\nJobs finished {settled}/{len(jobs)}", style="bold")
    if width >= 65:
        steps = int(20 * settled / len(jobs)) if jobs else 0
        header.append("  " + "━" * steps + "─" * (20 - steps), style="cyan")
    compact = height < 20
    table = Table(box=None, padding=(0, 1), expand=True, show_header=True)
    if width >= 48:
        table.add_column("#", width=3, style="dim")
    table.add_column("Download", ratio=1, no_wrap=True, overflow="ellipsis")
    if width >= 85:
        table.add_column("Type", width=5)
    table.add_column("Progress" if width >= 65 else "%", width=15 if width >= 65 else 4, no_wrap=True)
    if width >= 65:
        table.add_column("Speed", width=10, justify="right", no_wrap=True)
    if width >= 100:
        table.add_column("ETA", width=8, justify="right", no_wrap=True)
    table.add_column("Stage", width=7 if width < 48 else 11, no_wrap=True)
    styles = {"downloading": "cyan", "queued": "dim", "done": "green", "failed": "red"}
    labels = {"downloading": "Active", "queued": "Queued", "done": "Done", "failed": "Failed"}
    for job in visible:
        cells = []
        if width >= 48:
            cells.append(Text(str(job.id), style="dim"))
        title = terminal_text(job.title or job.url)
        if job.item_index and job.item_count:
            title = f"{job.item_index}/{job.item_count}  {title}"
        cells.append(Text(title, overflow="ellipsis", no_wrap=True))
        if width >= 85:
            cells.append(Text(job.mode.title(), style="dim"))
        pct = max(0, min(100, job.progress))
        waiting = job.status == "queued" or (job.status == "downloading" and job.phase == "Preparing")
        progress = "   —" if waiting else f"{pct:3.0f}%"
        if width >= 65 and not waiting:
            eighths = int(pct * 80 / 100)
            whole, part = divmod(eighths, 8)
            bar = "█" * whole + ("▏▎▍▌▋▊▉"[part - 1] if part else "")
            progress = bar + "░" * (10 - len(bar)) + f" {pct:3.0f}%"
        cells.append(Text(progress, style=styles.get(job.status, "white")))
        if width >= 65:
            cells.append(Text(terminal_text(job.speed) or "—", style="dim"))
        if width >= 100:
            cells.append(Text(terminal_text(job.eta) if job.status == "downloading" and job.phase == "Downloading" and job.eta else "—", style="dim"))
        stage = job.phase if job.status == "downloading" else "Waiting" if job.status == "queued" and job.phase == "Waiting" else labels.get(job.status, job.status.title())
        if width < 48 and stage == "Downloading":
            stage = "Active"
        cells.append(Text(terminal_text(stage), style=styles.get(job.status, "white")))
        table.add_row(*cells)
    if not visible:
        cells = [Text("—") for _ in table.columns]
        cells[1 if width >= 48 else 0] = Text(empty, style="dim")
        table.add_row(*cells)
    hidden = len(selected) - len(visible)
    queue_title = "Failed downloads" if view == "failed" else "Active downloads" if view == "active" else "Downloads"
    if pages > 1:
        queue_title += f" • {hidden} more • " + ("Page " if width >= 65 else "") + f"{page + 1}/{pages}"
    parts = [Panel(header, border_style="cyan", padding=(0, 1)),
             Panel(table, title=Text(queue_title), border_style="dim", padding=(0, 0))]
    if not compact:
        failures = [f"#{job.id}: {terminal_text(job.error)}" for job in selected if job.status == "failed" and job.error]
        activity = failures[-2:] if failures else [terminal_text(line) for line in logs[-2:]]
        activity_text = Text("\n".join(activity or ["Preparing downloads…"]), no_wrap=True, overflow="ellipsis")
        if len(activity) < 2:
            activity_text.append("\n")
        parts.append(Panel(activity_text, title=Text("Errors" if failures else "Activity"),
                           border_style="red" if failures else "dim", padding=(0, 1)))
    footer = Text("N/P pages • F failed • A all • D active • Q stop", style="dim", no_wrap=True, overflow="ellipsis")
    if not compact:
        profile = config.format.upper() if mode == "audio" else config.video_format.upper() if mode == "video" else "AUTO"
        footer.append(f"\n{profile} • Output: ")
        footer.append(terminal_text(output_dir), style="cyan")
    parts.append(Panel(footer, border_style="dim", padding=(0, 1)))
    return Group(*parts)


def run_tui(urls: List[str], output_dir: Path, engine: DownloadEngine, config: Config,
            mode: str = "auto", playlist: bool = False, print_debug: bool = False,
            explicit_mode: bool = False, retry_with_update: bool = False) -> Optional[bool]:
    """One renderer; bounded refresh and responsive input independent of download speed."""
    global _shutdown_requested
    if not DependencyInstaller.ensure_rich():
        return None
    try:
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text
        from rich.prompt import Prompt
    except ImportError:
        return None
    console = Console(no_color=Logger.NO_COLOR)
    urls = list(urls)
    if not urls:
        try:
            mode = choose_download_mode(mode, explicit_mode, rich_prompt=Prompt)
            entered = Prompt.ask("URL", default="", console=console).strip()
            if not entered:
                return True
            urls = parse_url_input(entered)
        except (KeyboardInterrupt, EOFError):
            return False
        except ValueError as exc:
            console.print(Text(str(exc), style="red"))
            return False
    try:
        urls = list(dict.fromkeys(validate_download_url(url) for url in urls))
    except ValueError as exc:
        console.print(Text(str(exc), style="red"))
        return False
    tracker = DownloadTracker()
    previous_tracker = engine.tracker
    engine.tracker = tracker
    jobs = {url: tracker.add_job(url, mode=ModeDetector.detect_mode(url) if mode == "auto" else mode) for url in urls}
    def worker():
        try:
            engine.batch_parallel(urls, output_dir, config.workers, mode, playlist,
                                  pre_allocated_jobs=jobs, print_debug=print_debug,
                                  retry_with_update=retry_with_update)
        except BaseException as exc:
            detail = terminal_text(exc) or type(exc).__name__
            tracker.add_log(f"error: {detail}")
            with tracker.lock:
                for job in tracker.jobs.values():
                    if job.status not in ("done", "failed"):
                        tracker.update_job(job.id, status="failed", error=detail)
        finally:
            with tracker.lock:
                for job in tracker.jobs.values():
                    if job.status not in ("done", "failed"):
                        tracker.update_job(job.id, status="failed", error="interrupted" if _shutdown_requested else "worker stopped")
    download_thread = threading.Thread(target=worker, daemon=True, name="Blaze downloads")
    session_started = time.monotonic()
    page, view = 0, "all"
    last_frame, last_refresh = None, 0.0
    refresh_rate = max(1, min(12, int(config.tui_refresh_rate)))
    try:
        layout = build_terminal_dashboard(tracker, config, output_dir, mode, engine.has_aria2c, console.width, console.height)
        with Logger.dashboard(tracker), dashboard_keys() as poll_key, Live(
                layout, console=console, refresh_per_second=refresh_rate, auto_refresh=False,
                screen=console.is_terminal, transient=console.is_terminal, vertical_overflow="crop") as live:
            download_thread.start()
            while True:
                key = poll_key()
                if key in ("\x03", "q"):
                    _shutdown_requested = True
                    raise KeyboardInterrupt
                if key == "n":
                    page += 1
                elif key == "p":
                    page -= 1
                elif key in ("f", "a", "d"):
                    view = {"f": "failed", "a": "all", "d": "active"}[key]
                    page = 0
                now = time.monotonic()
                dimensions = (console.width, console.height)
                frame = (tracker.revision, dimensions, int(now - session_started), page, view)
                finished = not download_thread.is_alive()
                if frame != last_frame and (key or finished or now - last_refresh >= 1.0 / refresh_rate):
                    layout = build_terminal_dashboard(tracker, config, output_dir, mode, engine.has_aria2c,
                                                      *dimensions, now - session_started, page=page, view=view)
                    live.update(layout, refresh=True)
                    last_frame, last_refresh = frame, now
                if finished:
                    break
                time.sleep(0.05)
    finally:
        if download_thread.is_alive():
            _shutdown_requested = True
            _kill_all_active_processes()
        if download_thread.ident is not None:
            download_thread.join(timeout=10.0)
        engine.tracker = previous_tracker
    queued, active, done, failed = tracker.get_stats()
    if not Logger.QUIET:
        summary = Text("\nComplete: ")
        summary.append(f"{done} succeeded", style="green")
        summary.append(f", {failed} failed", style="red" if failed else "dim")
        console.print(summary)
        with tracker.lock:
            failures = [replace(job) for job in tracker.jobs.values() if job.status == "failed"]
        for job in failures[:5]:
            console.print(Text(f"#{job.id}: {terminal_text(job.error) or 'Download failed; see Reports'}", style="red"))
        if len(failures) > 5:
            console.print(Text(f"{len(failures) - 5} additional failures; see Reports.", style="dim"))
        console.print(Text(f"Files saved to: {output_dir}"))
    return not (failed or queued or active or _shutdown_requested)


# ═══════════════════════════════════════════════════════════════════════
# URL UTILITIES
# ═══════════════════════════════════════════════════════════════════════

class URLParser:
    @staticmethod
    def from_file(path: str) -> List[str]:
        if not path:
            Logger.error("No URL file provided")
            sys.exit(1)
        expanded_path = os.path.expanduser(path)
        if not os.path.isfile(expanded_path):
            Logger.error(f"File not found: {expanded_path}")
            sys.exit(1)
        urls: List[str] = []
        try:
            with open(expanded_path, "r", encoding="utf-8-sig", errors="replace") as f:
                for raw in f:
                    line = raw.strip()
                    # Ignore blank lines, normal comments, and comments with leading whitespace
                    if not line or line.lstrip().startswith("#"):
                        continue
                    urls.append(line)
        except Exception as e:
            Logger.error(f"Cannot read URL file: {e}")
            sys.exit(1)
        if not urls:
            Logger.error("No valid URLs found in file")
            sys.exit(1)
        return urls


# ═══════════════════════════════════════════════════════════════════════
# INTERACTIVE PROMPTS
# ═══════════════════════════════════════════════════════════════════════

def parse_url_input(entered: str) -> List[str]:
    """Parse pasted URLs without interpreting backslashes as shell escapes."""
    tokens = shlex.split(entered, posix=False)
    urls = []
    for token in tokens:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
            token = token[1:-1]
        urls.append(validate_download_url(token))
    return list(dict.fromkeys(urls))


def choose_download_mode(current_mode: str, explicit_mode: bool, rich_prompt=None) -> str:
    if explicit_mode:
        return current_mode

    prompt = "Download type [1 Audio / 2 Video / 3 Auto]"
    choices = {
        "": current_mode if current_mode in ("audio", "video", "auto") else "auto",
        "1": "audio",
        "a": "audio",
        "audio": "audio",
        "2": "video",
        "v": "video",
        "video": "video",
        "3": "auto",
        "auto": "auto",
    }

    while True:
        try:
            if rich_prompt is not None:
                default = {"audio": "1", "video": "2"}.get(current_mode, "3")
                raw = rich_prompt.ask(prompt, default=default).strip().lower()
            else:
                raw = input(f"{prompt} (Enter = {choices[''].title()})\n> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            raise
        if raw in choices:
            return choices[raw]
        print("Please choose 1, 2, or 3.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            raw = input(f"{prompt} {suffix} ").strip().lower()
        except EOFError:
            return False
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer y or n.")


def ask_yes_no_rich(confirm, prompt: str, default: bool = False) -> bool:
    try:
        return bool(confirm.ask(prompt, default=default))
    except EOFError:
        return False


def snapshot_video_files(folder: Path) -> Dict[Path, float]:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        return {}
    files = {}
    for item in folder.iterdir():
        try:
            if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                files[item] = item.stat().st_mtime
        except OSError:
            continue
    return files


def newest_video_after(folder: Path, before: Dict[Path, float]) -> Optional[Path]:
    candidates = []
    for item in Path(folder).expanduser().glob("*"):
        try:
            if not item.is_file() or item.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            old_mtime = before.get(item)
            new_mtime = item.stat().st_mtime
            if old_mtime is None or new_mtime > old_mtime:
                candidates.append((new_mtime, item))
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def ensure_mpv() -> Optional[str]:
    mpv = DependencyInstaller._which("mpv")
    if mpv and DependencyInstaller._command_runs("mpv", ["--version"]):
        return mpv
    Logger.warn(f"Optional player unavailable. Place a portable mpv binary in {LOCAL_BIN_DIR} to enable playback.")
    return None


def play_video_with_mpv(video_path: Path):
    mpv = ensure_mpv()
    if not mpv:
        return
    try:
        subprocess.Popen([mpv, "--force-window=yes", "--", str(video_path)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=(sys.platform != "win32"))
        Logger.success(f"Playing: {video_path.name}")
    except Exception as e:
        Logger.warn(f"Could not open mpv: {e}")


def interactive_download_loop(engine: DownloadEngine, runtime_config: Config, base_output_dir: Path,
                              explicit_mode: bool, initial_mode: str, playlist: bool,
                              print_debug: bool, retry_with_update: bool, use_tui: bool = True) -> int:
    any_failed = False
    rich_console = rich_prompt = rich_confirm = None
    if use_tui and DependencyInstaller.ensure_rich():
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.text import Text
            from rich.prompt import Prompt, Confirm
            rich_console = Console(no_color=Logger.NO_COLOR)
            rich_prompt = Prompt
            rich_confirm = Confirm
            rich_console.print(Panel(Text("Blaze is ready. Choose a type, paste a URL, download, repeat.", style="cyan"),
                                     title="Blaze", border_style="cyan"))
        except Exception:
            rich_console = rich_prompt = rich_confirm = None

    while True:
        try:
            mode = choose_download_mode(initial_mode, explicit_mode, rich_prompt=rich_prompt)
            if rich_prompt is not None:
                entered = rich_prompt.ask("URL", default="").strip()
            else:
                prompt_text = f"\n{Style.BOLD}{Style.CYAN}Enter Video/Audio URL(s):{Style.RESET}\n{Style.DIM}(Paste URL, multiple separated by space, or press Enter to quit){Style.RESET}\n> "
                entered = input(prompt_text).strip()
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130
        except EOFError:
            return 1 if any_failed else 0

        if not entered:
            Logger.info("No URL entered. Exiting.")
            return 1 if any_failed else 0

        try:
            urls = parse_url_input(entered)
        except ValueError as e:
            Logger.error(f"Bad URL input: {e}")
            any_failed = True
            continue

        if not urls:
            continue

        try:
            urls = list(dict.fromkeys(validate_download_url(url) for url in urls))
        except ValueError as exc:
            Logger.error(str(exc))
            any_failed = True
            continue
        effective_mode_for_folder = mode if mode in ("audio", "video") else ModeDetector.detect_mode(urls[0])
        has_audio = mode == "audio" or (mode == "auto" and any(ModeDetector.detect_mode(url) == "audio" for url in urls))
        if has_audio and not getattr(runtime_config, "_explicit_format", False):
            try:
                while True:
                    prompt = "Audio format [1 MP3 / 2 WAV / 3 FLAC / 4 OPUS / 5 M4A / 6 OGG]"
                    choice = (rich_prompt.ask(prompt, default="1") if rich_prompt is not None else input(prompt + " (Enter = MP3): ")).strip().lower()
                    options = {"": "mp3", "1": "mp3", "2": "wav", "3": "flac", "4": "opus", "5": "m4a", "6": "ogg"}
                    choice = options.get(choice, choice)
                    if choice in ALLOWED_AUDIO_FORMATS:
                        runtime_config.format = choice
                        break
                    print("Choose 1–6 or enter a format name.")
            except (EOFError, KeyboardInterrupt):
                return 130
        video_dir = output_dir_for_mode(base_output_dir, "video")
        before_videos = snapshot_video_files(video_dir) if effective_mode_for_folder == "video" and len(urls) == 1 else {}

        dashboard_result = (run_tui(urls, base_output_dir, engine, runtime_config,
                                    mode=mode, playlist=playlist,
                                    print_debug=print_debug, explicit_mode=True,
                                    retry_with_update=retry_with_update) if use_tui else None)
        if dashboard_result is not None:
            failed = not dashboard_result
        elif len(urls) == 1:
            failed = not engine.download(urls[0], base_output_dir, mode=mode, playlist=playlist,
                                         show_progress=True, print_debug=print_debug,
                                         retry_with_update=retry_with_update)
        else:
            _, failed_count = engine.batch_parallel(urls, base_output_dir, runtime_config.workers,
                                                    mode=mode, playlist=playlist,
                                                    print_debug=print_debug,
                                                    retry_with_update=retry_with_update)
            failed = failed_count > 0

        any_failed = any_failed or failed
        if _shutdown_requested:
            return 130

        if not failed and effective_mode_for_folder == "video" and len(urls) == 1:
            video_file = newest_video_after(video_dir, before_videos)
            if video_file:
                play_prompt = f"Should Blaze play the video? ({video_file.name})"
                wants_play = ask_yes_no_rich(rich_confirm, Text(play_prompt), default=False) if rich_confirm is not None else ask_yes_no(play_prompt, default=False)
                if wants_play:
                    play_video_with_mpv(video_file)

        again = ask_yes_no_rich(rich_confirm, "Download another?", default=True) if rich_confirm is not None else ask_yes_no("Download another?", default=True)
        if not again:
            return 1 if any_failed else 0
        initial_mode = mode


# ═══════════════════════════════════════════════════════════════════════
# DOCTOR
# ═══════════════════════════════════════════════════════════════════════

def run_doctor() -> int:
    rows = []

    def add(name: str, version: str, ok: bool, note: str = "", status: Optional[str] = None):
        rows.append((name, version, status or ("OK" if ok else "FAIL"), note))

    def command_version(cmd: str, args: List[str]) -> Tuple[str, bool]:
        path = DependencyInstaller._which(cmd)
        if not path:
            return "missing", False
        try:
            result = subprocess.run([path] + args, capture_output=True, text=True,
                                    stdin=subprocess.DEVNULL, timeout=12)
            text = (result.stdout or result.stderr).strip().splitlines()
            return (text[0] if text else path), result.returncode == 0
        except Exception as e:
            return str(e), False

    add("Blaze", VERSION, True)
    python_private = Path(sys.prefix).resolve().is_relative_to(BLAZE_RUNTIME_DIR.resolve())
    py_ok = sys.version_info >= (3, 10)
    py_note = "manual Python install" if not python_private else "private runtime"
    if not py_ok:
        py_note = "Python 3.10+ required; automatic system installation disabled"
    add("Python", platform.python_version(), py_ok, py_note)

    for name, args, required, note in (
        ("yt-dlp", ["--version"], True, ""),
        ("ffmpeg", ["-version"], True, ""),
        ("ffprobe", ["-version"], False, "optional media inspection; FFmpeg remains available"),
        ("aria2c", ["--version"], False, "automatic private installation; --no-aria2c opts out"),
        ("mpv", ["--version"], False, "optional video playback prompt"),
    ):
        version, ok = command_version(name, args)
        add(name, version, ok or not required, note if not ok else note, status=None if required or ok else "OPTIONAL")

    # Rich/TUI
    try:
        import rich
        add("Rich", getattr(rich, "__version__", "installed"), True)
    except Exception:
        add("Rich", "missing", True, "auto-installs when TUI used", status="AUTO")

    # mutagen thumbnail support
    try:
        import mutagen
        add("mutagen", getattr(mutagen, "__version__", "installed"), True, "thumbnail embedding available")
    except Exception:
        add("mutagen", "missing", True, "auto-installs when needed", status="AUTO")

    # Config validity
    try:
        Config.load()
        add("Config", "", True)
    except Exception as e:
        add("Config", "", False, str(e))

    # Download folder write access
    doctor_config = Config.load()
    doctor_config.ensure_default_output()
    output_dir = Path(doctor_config.output_dir).expanduser()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".blaze-write-test-", dir=str(output_dir), delete=True) as probe:
            probe.write(b"ok")
            probe.flush()
        add("Download folder", str(output_dir), True)
    except Exception as e:
        add("Download folder", "", False, str(e))

    # PATH/wrapper correctness
    wrapper = shutil.which("blaze")
    found_in_path = wrapper is not None
    add("PATH/wrapper", str(wrapper or "not found"), True, "" if found_in_path else "optional when running the .py directly", status=None if found_in_path else "OPTIONAL")

    # Network reachability
    try:
        req = urllib.request.Request("https://github.com/", headers={"User-Agent": f"Blaze/{VERSION}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            add("Network", f"HTTP {getattr(resp, 'status', 'OK')}", 200 <= getattr(resp, "status", 200) < 500)
    except Exception as e:
        add("Network", "", False, str(e))

    # Cookie/browser availability if auth configured
    config = Config.load()
    config.ensure_default_output()
    if config.cookies_browser or config.cookies_file:
        if config.cookies_file:
            add("Cookie file", config.cookies_file, os.path.isfile(config.cookies_file))
        if config.cookies_browser:
            # Check if browser profile exists
            home = Path.home()
            browser_paths = {
                "safari": [home / "Library" / "Containers" / "com.apple.Safari" / "Data" / "Library" / "Cookies"],
                "chrome": [home / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies",
                           home / ".config" / "google-chrome" / "Default" / "Cookies",
                           home / ".config" / "chromium" / "Default" / "Cookies"],
                "firefox": [home / ".mozilla" / "firefox"],
                "brave": [home / "Library" / "Application Support" / "BraveSoftware" / "Brave-Browser" / "Default" / "Cookies",
                          home / ".config" / "BraveSoftware" / "Brave-Browser" / "Default" / "Cookies"],
                "edge": [home / "Library" / "Application Support" / "Microsoft Edge" / "Default" / "Cookies",
                         home / ".config" / "microsoft-edge" / "Default" / "Cookies",
                         home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies"],
            }
            found_browser = False
            paths = browser_paths.get(config.cookies_browser, [])
            for p in paths:
                if p.exists():
                    found_browser = True
                    break
            add("Browser cookies", config.cookies_browser, found_browser)
    else:
        add("Auth", "", True, "no auth configured")

    # Speed preset
    add("Speed", config.speed, True, f"preset: {config.speed}")

    width_name = max(len(r[0]) for r in rows)
    width_ver = min(48, max(len(str(r[1])) for r in rows))
    for name, version, status, note in rows:
        version = str(version)
        if len(version) > width_ver:
            version = version[:width_ver - 1] + "…"
        extra = f"  {note}" if note else ""
        print(f"{name:<{width_name}}  {version:<{width_ver}}  {status}{extra}")

    failures = [r for r in rows if r[2] == "FAIL"]
    if failures:
        print("\nBlaze needs attention.")
        return 1
    print("\nBlaze is ready.")
    return 0


# ═══════════════════════════════════════════════════════════════════════
# CLI ARGUMENT PARSING
# ═══════════════════════════════════════════════════════════════════════

def _build_epilog() -> str:
    if Logger.NO_COLOR:
        return """
EXAMPLES:
  blaze "https://youtube.com/watch?v=..."          # single video
  blaze "https://..."                              # auto TUI dashboard
  blaze -p "https://youtube.com/playlist?..."     # full playlist
  blaze -i urls.txt -w 6                         # batch + auto TUI
  blaze -F flac -Q 0 "https://..."                 # FLAC, best quality
  blaze --mode video "https://..."                # force video mode
  blaze --no-tui "https://..."                    # force plain output
  blaze --speed max -w 8 "https://..."            # aggressive, parallel
  blaze --retry-with-update "https://..."         # retry with update
  blaze --print-debug "https://..."               # show full command
  blaze --check-update                             # check yt-dlp updates
  blaze --doctor                                   # health check
  blaze --config                                   # edit settings

INSTALL:
  Download and extract the Windows or Mac installer ZIP.
  Run Install-Blaze.bat or Install-Blaze.command.

TUI MODE:
  Blaze opens the live dashboard automatically in Terminal.
  Rich auto-installs the first time TUI mode is used.

CONFIG:  ~/Blaze/Config/config.json
SITES:   YouTube, SoundCloud, Bandcamp, Vimeo, Twitter/X, TikTok,
        Reddit, Instagram, Facebook, and 1000+ more.
"""
    return f"""
{Style.BOLD}EXAMPLES:{Style.RESET}
  {Style.CYAN}blaze{Style.RESET} "https://youtube.com/watch?v=..."          # single video
  {Style.CYAN}blaze{Style.RESET} "https://..."                              # auto TUI dashboard
  {Style.CYAN}blaze{Style.RESET} -p "https://youtube.com/playlist?..."     # full playlist
  {Style.CYAN}blaze{Style.RESET} -i urls.txt -w 6                         # batch + auto TUI
  {Style.CYAN}blaze{Style.RESET} -F flac -Q 0 "https://..."                 # FLAC, best quality
  {Style.CYAN}blaze{Style.RESET} --mode video "https://..."                # force video mode
  {Style.CYAN}blaze{Style.RESET} --no-tui "https://..."                    # force plain output
  {Style.CYAN}blaze{Style.RESET} --speed max -w 8 "https://..."            # aggressive, parallel
  {Style.CYAN}blaze{Style.RESET} --retry-with-update "https://..."         # retry with update
  {Style.CYAN}blaze{Style.RESET} --print-debug "https://..."               # show full command
  {Style.CYAN}blaze{Style.RESET} --check-update                             # check yt-dlp updates
  {Style.CYAN}blaze{Style.RESET} --doctor                                   # health check
  {Style.CYAN}blaze{Style.RESET} --config                                   # edit settings

{Style.BOLD}INSTALL:{Style.RESET}
  Download and extract the Windows or Mac installer ZIP.
  Run Install-Blaze.bat or Install-Blaze.command.

{Style.BOLD}TUI MODE:{Style.RESET}
  Blaze opens the live dashboard automatically in Terminal.
  Rich auto-installs the first time TUI mode is used.

{Style.BOLD}CONFIG:{Style.RESET}  ~/Blaze/Config/config.json
{Style.BOLD}SITES:{Style.RESET}   YouTube, SoundCloud, Bandcamp, Vimeo, Twitter/X, TikTok,
        Reddit, Instagram, Facebook, and 1000+ more.
"""


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blaze",
        description="Universal Terminal downloader — audio + video, zero-config, auto-installs dependencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_epilog(),
    )
    parser.add_argument("url", nargs="*", help="Video/audio URL(s) — multiple accepted")
    parser.add_argument("-o", "--output", metavar="DIR", help="Output directory")
    parser.add_argument("-p", "--playlist", action="store_true", help="Download entire playlist")
    parser.add_argument("-i", "--input-file", metavar="FILE", help="Batch file (one URL per line)")
    parser.add_argument("-w", "--workers", type=int, metavar="N", help=f"Parallel workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("-F", "--format", metavar="FMT",
                        choices=["wav", "flac", "mp3", "opus", "m4a", "ogg"],
                        help="Audio format (default: wav)")
    parser.add_argument("-Q", "--audio-quality", metavar="Q", help="Audio quality 0 (best) to 10 (smallest); 0 for lossless")
    parser.add_argument("--mode", choices=["audio", "video", "auto"], default=None, help="Download mode (default: auto)")
    parser.add_argument("--fragments", type=int, metavar="N", help=f"Concurrent fragments per download (default: {DEFAULT_FRAGMENTS})")
    parser.add_argument("--video-format", choices=["mp4", "mkv", "best"], default=None, help="Video output container")
    parser.add_argument("--video-resolution", choices=["any", "1080p", "4k", "8k"], default=None, help="Video resolution limit")
    parser.add_argument("--no-aria2c", action="store_true", help="Disable aria2c downloader")
    parser.add_argument("--install-deps", action="store_true", help="Install and verify Blaze dependencies in its private runtime")
    parser.add_argument("--insecure", action="store_true", help="Disable SSL certificate verification")
    parser.add_argument("--speed", choices=["safe", "fast", "max"], default=None, help="Speed preset")
    parser.add_argument("--no-tui", action="store_true", help="Force plain output instead of the automatic TUI dashboard")
    parser.add_argument("--print-debug", action="store_true", help="Print the exact yt-dlp command for each download")
    parser.add_argument("--retry-with-update", action="store_true", help="On extractor failure, update yt-dlp and retry once")
    parser.add_argument("--ignore-history", action="store_true", help="Bypass saved history to recover missing files from older runs; existing files are kept")
    parser.add_argument("--tui", action="store_true", help="Launch rich TUI dashboard")
    parser.add_argument("--check-update", action="store_true", help="Check for yt-dlp updates manually")
    parser.add_argument("--cookies", metavar="FILE", help="Path to cookies file (Netscape format)")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", choices=["safari", "chrome", "firefox", "brave", "edge"],
                        help="Extract cookies from browser")
    parser.add_argument("--auth", metavar="BROWSER", choices=["safari", "chrome", "firefox", "brave", "edge"],
                        help="Shortcut for --cookies-from-browser")
    parser.add_argument("--doctor", action="store_true", help="Check Blaze runtime, dependencies, config, PATH, and network")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--config", action="store_true", help="Open config file in default editor")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


# ═══════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════

def open_config_editor(editor: str) -> int:
    """Launch EDITOR with arguments, including quoted Windows executable paths."""
    try:
        command = shlex.split(editor, posix=(sys.platform != "win32"))
        if sys.platform == "win32":
            command = [part[1:-1] if len(part) >= 2 and part[0] == part[-1]
                       and part[0] in ("'", '"') else part for part in command]
        if not command or not command[0]:
            raise ValueError("EDITOR is empty")
        code = subprocess.call(command + [str(CONFIG_FILE)])
        if code:
            Logger.error(f"Config editor exited with code {code}")
        return 0 if code == 0 else 1
    except (OSError, ValueError) as exc:
        Logger.error(f"Cannot open config editor: {exc}")
        return 1


def main():
    # Initial color setup
    Logger.NO_COLOR = "--no-color" in sys.argv or (os.environ.get("NO_COLOR", "") != "") or not sys.stdout.isatty()
    Logger.QUIET = "--quiet" in sys.argv or "-q" in sys.argv
    DependencyInstaller._add_venv_to_environment()

    parser = create_parser()
    args = parser.parse_args()

    Logger.QUIET = args.quiet
    Logger.NO_COLOR = args.no_color or (os.environ.get("NO_COLOR", "") != "") or not sys.stdout.isatty()
    if Logger.NO_COLOR:
        for name, value in vars(Style).copy().items():
            if name.isupper() and isinstance(value, str):
                setattr(Style, name, "")

    DependencyInstaller.ensure_modern_python_or_reexec()

    if args.check_update:
        Logger.banner()
        Logger.info("Ensuring yt-dlp is available...")
        ytdlp_cmd = DependencyInstaller._ensure_ytdlp()
        updated = UpdateChecker.check_ytdlp(ytdlp_cmd)
        sys.exit(1 if updated is None else 0)

    if args.doctor:
        sys.exit(run_doctor())

    if args.install_deps:
        Logger.banner()
        DependencyInstaller._ensure_local_bin_in_path()
        DependencyInstaller._ensure_ytdlp()
        DependencyInstaller._ensure_ffmpeg()
        # Setup fails visibly if either requested dependency is unavailable.
        checks = [("aria2c", DependencyInstaller._ensure_aria2c(private_only=True)),
                  ("Rich", DependencyInstaller.ensure_rich()),
                  ("Mutagen", DependencyInstaller.ensure_mutagen())]
        for name, ready in checks:
            (Logger.success if ready else Logger.error)(f"{name}: {'ready' if ready else 'unavailable'}")
        sys.exit(0 if all(ready for _, ready in checks) else 1)

    Logger.banner()
    config = Config.load()

    if args.config:
        config.save()
        default_editor = "notepad" if sys.platform == "win32" else "nano"
        editor = os.environ.get("EDITOR", default_editor)
        Logger.info(f"Opening config: {CONFIG_FILE}")
        sys.exit(open_config_editor(editor))

    # Runtime-only overrides (do NOT modify config.json)
    runtime_config = Config.load()
    runtime_config.ensure_default_output()
    if args.output is not None:
        if not args.output.strip():
            Logger.error("Output directory cannot be empty")
            sys.exit(1)
        runtime_config.output_dir = os.path.expanduser(args.output.strip())
    if args.workers is not None:
        if not 1 <= args.workers <= 32:
            Logger.error("Workers must be between 1 and 32")
            sys.exit(1)
        runtime_config.workers = args.workers
    if args.fragments is not None:
        if not 1 <= args.fragments <= 64:
            Logger.error("Fragments must be between 1 and 64")
            sys.exit(1)
        runtime_config.fragments = args.fragments
    runtime_config._explicit_format = bool(args.format)
    if args.format:
        runtime_config.format = args.format.lower()
    if args.audio_quality is not None:
        audio_quality = str(args.audio_quality).strip()
        if not _valid_audio_quality(audio_quality):
            Logger.error("Audio quality must be a number between 0 and 10")
            sys.exit(1)
        runtime_config.audio_quality = audio_quality
    if args.no_aria2c:
        runtime_config.use_aria2c = False
    if args.ignore_history:
        runtime_config.ignore_history = True
    if args.insecure:
        runtime_config.insecure = True
    if args.speed:
        runtime_config.speed = args.speed
        if args.workers is None:
            runtime_config.workers = SPEED_CONFIG[args.speed]["workers"]
        if args.fragments is None:
            runtime_config.fragments = SPEED_CONFIG[args.speed]["fragments"]
    if args.video_format:
        runtime_config.video_format = args.video_format
    if args.video_resolution:
        if args.video_resolution == "any":
            runtime_config.video_resolution = ""
        else:
            runtime_config.video_resolution = args.video_resolution
    if args.cookies:
        runtime_config.cookies_file = os.path.expanduser(args.cookies)
        runtime_config.cookies_browser = ""
    if args.cookies_from_browser:
        runtime_config.cookies_browser = args.cookies_from_browser
        runtime_config.cookies_file = ""
    if args.auth:
        runtime_config.cookies_browser = args.auth
        runtime_config.cookies_file = ""

    urls: List[str] = []
    if args.input_file:
        urls.extend(URLParser.from_file(args.input_file))
    if args.url:
        urls.extend(args.url)

    urls = list(dict.fromkeys(urls))
    if not urls and not sys.stdin.isatty():
        parser.print_help()
        sys.exit(1)

    try:
        urls = list(dict.fromkeys(validate_download_url(url) for url in urls))
    except ValueError as exc:
        parser.error(str(exc))

    ytdlp_cmd, has_aria2c = DependencyInstaller.ensure_all(use_aria2c=runtime_config.use_aria2c)
    if has_aria2c:
        Logger.success("aria2c ready — parallel HTTP downloading enabled")
    elif runtime_config.use_aria2c:
        Logger.warn("aria2c unavailable — using native downloader")

    explicit_mode = any(arg == "--mode" or arg.startswith("--mode=") for arg in sys.argv[1:])
    mode = args.mode if args.mode is not None else runtime_config.mode
    use_tui = (args.tui or sys.stdout.isatty()) and not (args.no_tui or Logger.QUIET)

    if not urls:
        if sys.stdin.isatty():
            effective_speed = runtime_config.speed if runtime_config.speed in SPEED_PRESETS else args.speed
            engine = DownloadEngine(ytdlp_cmd, runtime_config, has_aria2c, tracker=None, speed=effective_speed)
            output_dir = Path(runtime_config.output_dir).expanduser()
            sys.exit(interactive_download_loop(engine, runtime_config, output_dir, explicit_mode,
                                               mode, args.playlist, args.print_debug,
                                               args.retry_with_update, use_tui=use_tui))
        else:
            parser.print_help()
            sys.exit(1)

    effective_speed = runtime_config.speed if runtime_config.speed in SPEED_PRESETS else args.speed
    engine = DownloadEngine(ytdlp_cmd, runtime_config, has_aria2c, tracker=None, speed=effective_speed)
    output_dir = Path(runtime_config.output_dir).expanduser()

    any_failed = False
    tui_ran = False

    if use_tui:
        tui_result = run_tui(urls, output_dir, engine, runtime_config, mode=mode,
                             playlist=args.playlist, print_debug=args.print_debug,
                             explicit_mode=explicit_mode,
                             retry_with_update=args.retry_with_update)
        tui_ran = tui_result is not None
        if tui_result is None:
            if len(urls) == 1:
                any_failed = not engine.download(urls[0], output_dir, mode=mode, playlist=args.playlist, show_progress=True,
                                                 print_debug=args.print_debug, retry_with_update=args.retry_with_update)
            else:
                _, failed = engine.batch_parallel(urls, output_dir, runtime_config.workers, mode=mode, playlist=args.playlist,
                                                  print_debug=args.print_debug, retry_with_update=args.retry_with_update)
                any_failed = failed > 0
        else:
            any_failed = not tui_result
    else:
        if len(urls) == 1:
            any_failed = not engine.download(urls[0], output_dir, mode=mode, playlist=args.playlist, show_progress=True,
                                             print_debug=args.print_debug, retry_with_update=args.retry_with_update)
        else:
            _, failed = engine.batch_parallel(urls, output_dir, runtime_config.workers, mode=mode, playlist=args.playlist,
                                              print_debug=args.print_debug, retry_with_update=args.retry_with_update)
            any_failed = failed > 0

    if not Logger.QUIET and not tui_ran:
        print(f"\n{Style.CYAN}{'═' * 60}{Style.RESET}")
        print(f"{Style.GREEN}{Style.BOLD}Session finished.{Style.RESET} Files saved to: {output_dir}")
        print(f"{Style.CYAN}{'═' * 60}{Style.RESET}\n")

    sys.exit(130 if _shutdown_requested else (1 if any_failed else 0))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        _kill_all_active_processes()
        sys.exit(130)

