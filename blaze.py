#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blaze v4.0.0 — Universal Audio Downloader
Extract lossless audio from 1000+ sites at maximum speed
Zero-config: auto-installs yt-dlp, ffmpeg & aria2c on first run
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
import tarfile
import zipfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, fields
from typing import List, Optional, Tuple, Dict

# ═══════════════════════════════════════════════════════════════════════
# METADATA
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "Blaze"
VERSION = "4.0.0"
DEFAULT_WORKERS = 4
DEFAULT_FRAGMENTS = 8
DEFAULT_OUTPUT = Path.home() / "Music" / "BlazeDownloads"
CONFIG_DIR = Path.home() / ".config" / APP_NAME.lower()
CONFIG_FILE = CONFIG_DIR / "config.json"
LOCAL_BIN_DIR = Path.home() / ".blaze" / "bin"

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

    @classmethod
    def _out(cls, symbol: str, color: str, title: str, message: str):
        if cls.QUIET:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        if cls.NO_COLOR:
            print(f"[{ts}] {symbol} {title}: {message}")
        else:
            print(f"{Style.DIM}[{ts}]{Style.RESET} {color}{symbol}{Style.RESET} {Style.BOLD}{title}:{Style.RESET} {message}")

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
        cls._out("x", Style.RED, "FAIL", msg)

    @classmethod
    def banner(cls):
        if cls.QUIET or cls.NO_COLOR:
            print(f"Blaze v{VERSION}")
            return

        width = 58
        bc = Style.CYAN + Style.BOLD
        rst = Style.RESET

        text1 = f"{Style.BOLD}Blaze{rst} v{VERSION}{Style.DIM} - Universal Audio Downloader{rst}"
        text2 = f"{Style.DIM}Zero-config. Auto-installs deps. Maximum speed.{rst}"

        def _pad(s, w):
            clean = re.sub(r"\x1B\[[0-9;]*m", "", s)
            return s + " " * max(0, w - len(clean))

        top = bc + "╔" + "═" * width + "╗" + rst
        m1 = bc + "║ " + rst + _pad(text1, width - 2) + " " + bc + "║" + rst
        m2 = bc + "║ " + rst + _pad(text2, width - 2) + " " + bc + "║" + rst
        bot = bc + "╚" + "═" * width + "╝" + rst

        print("\n" + top + "\n" + m1 + "\n" + m2 + "\n" + bot + "\n")

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
    retries: int = 3
    retry_delay: int = 5
    write_metadata: bool = True
    create_subdirs: bool = True
    tui_refresh_rate: int = 4

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                known = {f.name for f in fields(cls)}
                filtered = {k: v for k, v in data.items() if k in known}
                return cls(**filtered)
            except Exception:
                pass
        return cls()

# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY INSTALLER  (auto-install yt-dlp, ffmpeg, aria2c)
# ═══════════════════════════════════════════════════════════════════════

class DependencyInstaller:
    """Checks, downloads and installs all required binaries automatically."""

    _cache = {}

    @classmethod
    def _ensure_local_bin_in_path(cls):
        LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)
        local = str(LOCAL_BIN_DIR)
        current = os.environ.get("PATH", "")
        if local not in current.split(os.pathsep):
            os.environ["PATH"] = local + os.pathsep + current

    @classmethod
    def _which(cls, cmd: str) -> Optional[str]:
        if cmd in cls._cache:
            return cls._cache[cmd]
        path = shutil.which(cmd)
        cls._cache[cmd] = path
        return path

    @classmethod
    def _pip_install(cls, package: str, timeout: int = 180):
        """Install a Python package via pip."""
        Logger.info(f"Installing {package} via pip...")
        for extra in (["--user"] if sys.platform != "win32" else []):
            cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"] + extra + [package]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
                return
            except subprocess.CalledProcessError:
                continue
        # Last resort without --user
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", package]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)

    @classmethod
    def _install_via_package_manager(cls, pkg: str) -> bool:
        """Try system package managers."""
        plat = sys.platform
        if plat == "darwin" and cls._which("brew"):
            try:
                subprocess.run(["brew", "install", pkg], check=True, capture_output=True, timeout=300)
                return True
            except Exception:
                pass
        elif plat.startswith("linux"):
            if cls._which("apt"):
                try:
                    subprocess.run(["sudo", "apt", "install", "-y", pkg],
                                   check=True, capture_output=True, timeout=300)
                    return True
                except Exception:
                    pass
            if cls._which("pacman"):
                try:
                    subprocess.run(["sudo", "pacman", "-S", "--noconfirm", pkg],
                                   check=True, capture_output=True, timeout=300)
                    return True
                except Exception:
                    pass
            if cls._which("dnf"):
                try:
                    subprocess.run(["sudo", "dnf", "install", "-y", pkg],
                                   check=True, capture_output=True, timeout=300)
                    return True
                except Exception:
                    pass
        elif plat == "win32":
            if cls._which("choco"):
                try:
                    subprocess.run(["choco", "install", pkg, "-y"],
                                   check=True, capture_output=True, timeout=300)
                    return True
                except Exception:
                    pass
            if cls._which("winget"):
                try:
                    subprocess.run(["winget", "install", "--silent", pkg],
                                   check=True, capture_output=True, timeout=300)
                    return True
                except Exception:
                    pass
        return False

    @classmethod
    def _download_and_extract(cls, url: str, target_name: str, is_zip: bool = False) -> bool:
        """Download a binary archive and extract the requested file to LOCAL_BIN_DIR."""
        try:
            suffix = ".zip" if is_zip else ".tar.bz2"
            dl_path = LOCAL_BIN_DIR / f"_dl_{target_name}{suffix}"
            Logger.info(f"Downloading {target_name}...")
            urllib.request.urlretrieve(url, dl_path)

            if is_zip:
                with zipfile.ZipFile(dl_path, "r") as zf:
                    for member in zf.namelist():
                        if target_name in member.split("/")[-1]:
                            zf.extract(member, LOCAL_BIN_DIR)
                            extracted = LOCAL_BIN_DIR / member
                            final = LOCAL_BIN_DIR / member.split("/")[-1]
                            if extracted.exists():
                                shutil.move(str(extracted), str(final))
                            break
            else:
                with tarfile.open(dl_path, "r:bz2") as tf:
                    for member in tf.getmembers():
                        if target_name in member.name.split("/")[-1]:
                            tf.extract(member, LOCAL_BIN_DIR)
                            extracted = LOCAL_BIN_DIR / member.name
                            final = LOCAL_BIN_DIR / member.name.split("/")[-1]
                            if extracted.exists():
                                shutil.move(str(extracted), str(final))
                            break

            dl_path.unlink(missing_ok=True)
            final_path = LOCAL_BIN_DIR / target_name
            if final_path.exists() and sys.platform != "win32":
                os.chmod(final_path, 0o755)
            return cls._which(target_name.split(".")[0]) is not None
        except Exception as e:
            Logger.warn(f"Download failed for {target_name}: {e}")
            return False

    @classmethod
    def _ensure_ytdlp(cls) -> str:
        """Ensure yt-dlp is available. Returns command string."""
        # 1. System binary
        if cls._which("yt-dlp"):
            return "yt-dlp"
        # 2. Python module
        try:
            result = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return f"{sys.executable} -m yt_dlp"
        except Exception:
            pass

        # 3. Auto-install
        Logger.info("yt-dlp not found — auto-installing...")
        cls._pip_install("yt-dlp")

        if cls._which("yt-dlp"):
            Logger.success("yt-dlp installed")
            return "yt-dlp"
        try:
            result = subprocess.run([sys.executable, "-m", "yt_dlp", "--version"],
                                    capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                Logger.success("yt-dlp installed (module mode)")
                return f"{sys.executable} -m yt_dlp"
        except Exception:
            pass

        Logger.error("Failed to auto-install yt-dlp. Please install manually: pip install yt-dlp")
        sys.exit(1)

    @classmethod
    def _ensure_ffmpeg(cls):
        """Ensure ffmpeg binary is available."""
        if cls._which("ffmpeg"):
            return

        Logger.info("ffmpeg not found — auto-installing...")

        # 1. Try imageio-ffmpeg (bundled static ffmpeg)
        try:
            cls._pip_install("imageio-ffmpeg")
            import imageio_ffmpeg
            bundled = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled and Path(bundled).exists():
                dest = LOCAL_BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
                if not dest.exists():
                    if sys.platform == "win32":
                        shutil.copy2(bundled, dest)
                    else:
                        os.symlink(bundled, dest)
                Logger.success("ffmpeg installed (bundled)")
                return
        except Exception:
            pass

        # 2. Try package manager
        if cls._install_via_package_manager("ffmpeg"):
            Logger.success("ffmpeg installed via package manager")
            return

        Logger.error("Failed to auto-install ffmpeg.")
        print(f"""
{Style.YELLOW}Manual install:{Style.RESET}
  macOS:   {Style.BOLD}brew install ffmpeg{Style.RESET}
  Linux:   {Style.BOLD}sudo apt install ffmpeg{Style.RESET}  (or pacman/dnf)
  Windows: {Style.BOLD}winget install Gyan.FFmpeg{Style.RESET}
""")
        sys.exit(1)

    @classmethod
    def _ensure_aria2c(cls) -> bool:
        """Ensure aria2c is available. Returns True if present/installed."""
        if cls._which("aria2c"):
            return True

        Logger.info("aria2c not found — auto-installing...")

        # 1. Package manager
        if cls._install_via_package_manager("aria2"):
            Logger.success("aria2c installed via package manager")
            return True

        # 2. Static binary from GitHub
        plat = sys.platform
        machine = platform.machine().lower()
        version = "1.37.0"
        base = f"https://github.com/aria2/aria2/releases/download/release-{version}"

        if plat == "darwin":
            # macOS static builds are x86_64; arm64 users should use brew (handled above)
            url = f"{base}/aria2-{version}-osx-darwin.tar.bz2"
            success = cls._download_and_extract(url, "aria2c", is_zip=False)
        elif plat.startswith("linux") and "x86_64" in machine:
            url = f"{base}/aria2-{version}-x86_64-linux-gnu.tar.bz2"
            success = cls._download_and_extract(url, "aria2c", is_zip=False)
        elif plat == "win32":
            url = f"{base}/aria2-{version}-win-64bit-build1.zip"
            success = cls._download_and_extract(url, "aria2c.exe", is_zip=True)
        else:
            success = False

        if success:
            Logger.success("aria2c installed (static binary)")
            return True

        Logger.warn("aria2c auto-install failed — falling back to native downloader")
        return False

    @classmethod
    def ensure_all(cls) -> Tuple[str, bool]:
        """Entry point. Returns (ytdlp_cmd, has_aria2c)."""
        cls._ensure_local_bin_in_path()
        ytdlp = cls._ensure_ytdlp()
        cls._ensure_ffmpeg()
        has_aria2c = cls._ensure_aria2c()
        return ytdlp, has_aria2c

# ═══════════════════════════════════════════════════════════════════════
# MANUAL UPDATE CHECKER
# ═══════════════════════════════════════════════════════════════════════

class UpdateChecker:
    @classmethod
    def check_ytdlp(cls, ytdlp_cmd: str) -> bool:
        try:
            Logger.info("Checking for yt-dlp updates...")
            result = subprocess.run(
                ytdlp_cmd.split() + ["-U"],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout + result.stderr

            if "up to date" in output.lower() or "already up" in output.lower():
                Logger.success("yt-dlp is up to date")
                return False
            elif "updated" in output.lower():
                Logger.success("yt-dlp was updated to latest version")
                return True
            else:
                Logger.warn("Could not determine update status")
                return False
        except subprocess.TimeoutExpired:
            Logger.warn("Update check timed out")
            return False
        except Exception as e:
            Logger.warn(f"Update check failed: {e}")
            return False

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

class DownloadTracker:
    def __init__(self):
        self.jobs: Dict[int, Job] = {}
        self.logs: List[str] = []
        self.lock = threading.Lock()
        self._counter = 0

    def add_job(self, url: str) -> int:
        with self.lock:
            self._counter += 1
            job = Job(id=self._counter, url=url)
            self.jobs[self._counter] = job
            return self._counter

    def update_job(self, job_id: int, **kwargs):
        with self.lock:
            if job_id in self.jobs:
                for k, v in kwargs.items():
                    setattr(self.jobs[job_id], k, v)

    def add_log(self, message: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs.append(f"[{ts}] {message}")
            if len(self.logs) > 100:
                self.logs = self.logs[-100:]

    def get_stats(self) -> Tuple[int, int, int, int]:
        with self.lock:
            queued = sum(1 for j in self.jobs.values() if j.status == "queued")
            active = sum(1 for j in self.jobs.values() if j.status == "downloading")
            done = sum(1 for j in self.jobs.values() if j.status == "done")
            failed = sum(1 for j in self.jobs.values() if j.status == "failed")
            return queued, active, done, failed

    def all_terminal(self) -> bool:
        with self.lock:
            return len(self.jobs) > 0 and all(
                j.status in ("done", "failed") for j in self.jobs.values()
            )

# ═══════════════════════════════════════════════════════════════════════
# DOWNLOAD ENGINE
# ═══════════════════════════════════════════════════════════════════════

class DownloadEngine:
    def __init__(self, ytdlp_cmd: str, config: Config, has_aria2c: bool, tracker: Optional[DownloadTracker] = None):
        self.ytdlp_cmd = ytdlp_cmd
        self.config = config
        self.has_aria2c = has_aria2c
        self.tracker = tracker
        self.interrupted = False
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        if not self.interrupted:
            self.interrupted = True
            Logger.warn("Interrupted by user. Finishing current downloads...")
        else:
            Logger.error("Force exit")
            sys.exit(130)

    def _build_flags(self, playlist: bool = False, show_progress: bool = True) -> List[str]:
        flags = [
            "--extract-audio",
            "--audio-format", self.config.format,
            "--audio-quality", self.config.audio_quality,
            "--format", "ba*",
            "--concurrent-fragments", str(max(1, self.config.fragments)),
            "--buffer-size", "16K",
            "--http-chunk-size", "10M",
            "--geo-bypass",
            "--no-check-certificates",
            "--no-warnings",
            "--newline",
        ]

        if show_progress:
            flags.append("--progress")

        flags += ["--continue", "--no-overwrites"]
        flags += ["--retries", str(self.config.retries), "--fragment-retries", str(self.config.retries)]

        if self.config.write_metadata:
            flags += ["--embed-metadata"]
            if self.config.format.lower() != "wav":
                flags += ["--embed-thumbnail"]

        if self.config.format.lower() == "wav":
            flags += ["--no-write-thumbnail"]

        if not playlist:
            flags += ["--no-playlist"]

        if self.config.use_aria2c and self.has_aria2c:
            flags += [
                "--downloader", "aria2c",
                "--downloader-args",
                "aria2c:-x 16 -s 16 -k 1M --file-allocation=none --optimize-concurrent-downloads=true"
            ]

        return flags

    def _get_output_template(self, output_dir: Path, playlist: bool = False) -> str:
        if playlist:
            subdir = "%(playlist_title)s" if self.config.create_subdirs else ""
            return str(output_dir / subdir / "%(playlist_index)03d - %(title).80s [%(id)s].%(ext)s")
        return str(output_dir / "%(title).100s [%(id)s].%(ext)s")

    def _extract_site(self, url: str) -> str:
        try:
            from urllib.parse import urlparse
            netloc = urlparse(url).netloc.lower()
            return netloc.replace("www.", "").split(":")[0]
        except Exception:
            return "unknown"

    def _parse_ytdlp_line(self, line: str, job_id: int):
        line = line.strip()
        if not line:
            return

        if "[info]" in line and "Downloading" in line:
            try:
                title = line.split("Downloading")[-1].strip().strip(":")
                if title and len(title) > 2:
                    self.tracker.update_job(job_id, title=title)
            except Exception:
                pass

        if "Destination:" in line:
            try:
                dest = line.split("Destination:")[-1].strip()
                fname = os.path.basename(dest)
                title = fname.rsplit(".", 1)[0].rsplit(" [", 1)[0]
                if title and len(title) > 2:
                    self.tracker.update_job(job_id, title=title)
            except Exception:
                pass

        if "%" in line and "of" in line:
            try:
                pct_str = line.split("%")[0].split()[-1]
                pct = float(pct_str)
                self.tracker.update_job(job_id, progress=pct)
            except (ValueError, IndexError):
                pass

        if "MiB/s" in line or "KiB/s" in line or "B/s" in line:
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if "B/s" in p and i > 0:
                        self.tracker.update_job(job_id, speed=parts[i-1] + " " + p)
                        break
            except Exception:
                pass

        lower = line.lower()
        if any(k in lower for k in ("error", "failed", "unable to", "not available", "blocked")):
            self.tracker.add_log(f"error: {line[:80]}")
        elif any(k in lower for k in ("warning", "deprecated", "unavailable")):
            self.tracker.add_log(f"warn: {line[:80]}")

    def download(self, url: str, output_dir: Path, playlist: bool = False,
                 job_id: Optional[int] = None, show_progress: bool = True) -> bool:
        if self.interrupted:
            return False

        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        template = self._get_output_template(output_dir, playlist)
        site = self._extract_site(url)

        if self.tracker and job_id:
            self.tracker.update_job(job_id, site=site, status="downloading")
            self.tracker.add_log(f"started: {url[:60]}...")

        if not self.tracker:
            print(f"\n{Style.CYAN}{'─'*60}{Style.RESET}")
            print(f"{Style.BOLD}Downloading:{Style.RESET} {Style.WHITE}{url[:70]}{Style.RESET}")
            print(f"{Style.DIM}Site:{Style.RESET} {site}  {Style.DIM}Format:{Style.RESET} {self.config.format.upper()}  {Style.DIM}Engine:{Style.RESET} {'aria2c' if (self.config.use_aria2c and self.has_aria2c) else 'native'}")
            print(f"{Style.CYAN}{'─'*60}{Style.RESET}")

        cmd = self.ytdlp_cmd.split() + self._build_flags(playlist, show_progress) + [
            "--output", template,
            url
        ]

        start = time.time()
        try:
            if self.tracker and job_id:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )

                try:
                    for line in process.stdout:
                        self._parse_ytdlp_line(line, job_id)
                finally:
                    process.stdout.close()

                process.wait()
                result_code = process.returncode
            else:
                result = subprocess.run(cmd, capture_output=False, text=True)
                result_code = result.returncode

            elapsed = time.time() - start

            if result_code == 0:
                if self.tracker and job_id:
                    self.tracker.update_job(job_id, status="done", progress=100.0, elapsed=elapsed)
                    self.tracker.add_log(f"completed in {elapsed:.1f}s: {url[:60]}...")
                else:
                    print(f"{Style.GREEN}+ Completed in {elapsed:.1f}s{Style.RESET}")
                return True
            else:
                if self.tracker and job_id:
                    self.tracker.update_job(job_id, status="failed", error=f"exit code {result_code}")
                    self.tracker.add_log(f"failed (code {result_code}): {url[:60]}...")
                else:
                    print(f"{Style.RED}x Failed (exit code {result_code}){Style.RESET}")
                return False

        except Exception as e:
            if self.tracker and job_id:
                self.tracker.update_job(job_id, status="failed", error=str(e))
                self.tracker.add_log(f"exception: {str(e)[:60]}")
            else:
                print(f"{Style.RED}x Exception: {e}{Style.RESET}")
            return False

    def batch_parallel(self, urls: List[str], output_dir: Path, max_workers: int, playlist: bool = False):
        output_dir = Path(output_dir).expanduser().resolve()
        total = len(urls)
        max_workers = max(1, min(max_workers, total))

        if not self.tracker:
            print(f"\n{Style.BOLD}{Style.CYAN}⚡ Parallel Batch Mode{Style.RESET}")
            print(f"{Style.DIM}URLs:{Style.RESET} {total}  {Style.DIM}Workers:{Style.RESET} {max_workers}  {Style.DIM}Output:{Style.RESET} {output_dir}\n")

        completed = 0
        failed = 0
        show_progress = self.tracker is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for url in urls:
                job_id = None
                if self.tracker:
                    job_id = self.tracker.add_job(url)
                future = executor.submit(self.download, url, output_dir, playlist, job_id, show_progress)
                futures[future] = url

            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                try:
                    if future.result():
                        completed += 1
                    else:
                        failed += 1
                except Exception as e:
                    Logger.error(f"{url}: {e}")
                    failed += 1

                if not self.tracker and not Logger.QUIET:
                    print(f"{Style.DIM}[{completed}/{total} completed, {failed} failed]{Style.RESET}")

        if not self.tracker:
            print(f"\n{Style.GREEN}{Style.BOLD}+ Batch complete:{Style.RESET} {completed} succeeded, {failed} failed")

# ═══════════════════════════════════════════════════════════════════════
# RICH TUI MODE
# ═══════════════════════════════════════════════════════════════════════

def run_tui(urls: List[str], output_dir: Path, engine: DownloadEngine, config: Config, playlist: bool = False):
    try:
        from rich.console import Console
        from rich.live import Live
        from rich.table import Table
        from rich.panel import Panel
        from rich.layout import Layout
        from rich.progress import Progress, BarColumn, TextColumn
        from rich.text import Text
        from rich.align import Align
    except ImportError:
        Logger.error("rich is not installed. Install it: pip install rich")
        Logger.info("Falling back to standard mode...")
        return False

    console = Console()
    tracker = DownloadTracker()
    engine.tracker = tracker

    download_thread = threading.Thread(
        target=engine.batch_parallel,
        args=(urls, output_dir, config.workers, playlist),
        daemon=True
    )
    download_thread.start()

    def make_layout() -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="jobs", ratio=2),
            Layout(name="logs", ratio=1)
        )
        return layout

    def render_header() -> Panel:
        queued, active, done, failed = tracker.get_stats()
        stats_text = Text()
        stats_text.append(f"Blaze v{VERSION}  ", style="bold cyan")
        stats_text.append(f"queued: {queued}  ", style="dim")
        stats_text.append(f"active: {active}  ", style="blue")
        stats_text.append(f"done: {done}  ", style="green")
        stats_text.append(f"failed: {failed}", style="red" if failed > 0 else "dim")
        return Panel(Align.center(stats_text), border_style="cyan", padding=(0, 1))

    def render_jobs() -> Panel:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("#", width=3, style="dim")
        table.add_column("title", min_width=20, no_wrap=True)
        table.add_column("progress", width=20)
        table.add_column("speed", width=14, justify="right")
        table.add_column("status", width=12, justify="center")

        with tracker.lock:
            jobs = sorted(tracker.jobs.values(), key=lambda j: j.id)

        for job in jobs:
            status_style = {
                "queued": "dim",
                "downloading": "blue",
                "done": "green",
                "failed": "red"
            }.get(job.status, "white")

            progress = Progress(
                BarColumn(bar_width=12, complete_style="cyan", finished_style="green"),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                expand=False
            )
            progress.add_task("", total=100, completed=job.progress)

            title = (job.title or job.url[:35] + "...") if len(job.title or job.url) > 38 else (job.title or job.url)
            speed = job.speed if job.speed else "—"

            table.add_row(
                str(job.id),
                title,
                progress,
                Text(speed, style="dim", justify="right"),
                Text(job.status.upper(), style=status_style)
            )

        return Panel(table, title="[bold]downloads", border_style="dim", padding=(0, 0))

    def render_logs() -> Panel:
        with tracker.lock:
            recent_logs = tracker.logs[-20:]
        log_text = Text("\n".join(recent_logs) if recent_logs else "waiting for activity...", style="dim")
        return Panel(log_text, title="[bold]activity log", border_style="dim", padding=(0, 1))

    def render_footer() -> Panel:
        engine_name = "aria2c" if (config.use_aria2c and engine.has_aria2c) else "native"
        footer_text = Text()
        footer_text.append(f"engine: {engine_name}  ", style="dim")
        footer_text.append(f"workers: {config.workers}  ", style="dim")
        footer_text.append(f"fragments: {config.fragments}  ", style="dim")
        footer_text.append(f"output: {output_dir}", style="dim")
        return Panel(Align.center(footer_text), border_style="dim", padding=(0, 1))

    def update_layout(layout: Layout):
        layout["header"].update(render_header())
        layout["jobs"].update(render_jobs())
        layout["logs"].update(render_logs())
        layout["footer"].update(render_footer())

    layout = make_layout()

    hang_detected_at = None
    HANG_TIMEOUT = 30.0

    with Live(layout, console=console, refresh_per_second=config.tui_refresh_rate, screen=True) as live:
        while True:
            update_layout(layout)

            thread_alive = download_thread.is_alive()
            has_active = any(j.status == "downloading" for j in tracker.jobs.values())
            all_done = tracker.all_terminal()

            if not thread_alive and all_done:
                break

            if not thread_alive and has_active:
                if hang_detected_at is None:
                    hang_detected_at = time.time()
                elif time.time() - hang_detected_at > HANG_TIMEOUT:
                    tracker.add_log("warn: download thread died unexpectedly — forcing exit")
                    for jid, job in tracker.jobs.items():
                        if job.status == "downloading":
                            tracker.update_job(jid, status="failed", error="thread died")
                    break
            else:
                hang_detected_at = None

            time.sleep(0.25)

        update_layout(layout)
        time.sleep(0.5)

    download_thread.join(timeout=2.0)
    engine.tracker = None

    queued, active, done, failed = tracker.get_stats()
    console.print(f"\n[bold green]+ Complete:[/bold green] {done} succeeded, [bold red]{failed} failed[/bold red]")
    console.print(f"[dim]Files saved to: {output_dir}[/dim]\n")

    return True

# ═══════════════════════════════════════════════════════════════════════
# URL UTILITIES
# ═══════════════════════════════════════════════════════════════════════

class URLParser:
    @staticmethod
    def from_file(path: str) -> List[str]:
        if not os.path.exists(path):
            Logger.error(f"File not found: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8-sig") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        if not urls:
            Logger.error("No valid URLs found in file")
            sys.exit(1)
        return urls

# ═══════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blaze",
        description="Universal audio downloader — zero-config, auto-installs dependencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
{Style.BOLD}EXAMPLES:{Style.RESET}
  {Style.CYAN}blaze{Style.RESET} "https://youtube.com/watch?v=..."          # single track
  {Style.CYAN}blaze{Style.RESET} --tui "https://..."                        # rich TUI dashboard
  {Style.CYAN}blaze{Style.RESET} -p "https://youtube.com/playlist?..."     # full playlist
  {Style.CYAN}blaze{Style.RESET} -i urls.txt -w 6 --tui                   # batch + TUI
  {Style.CYAN}blaze{Style.RESET} --check-update                             # manual update check
  {Style.CYAN}blaze{Style.RESET} --config                                   # edit settings

{Style.BOLD}INSTALL:{Style.RESET}
  chmod +x blaze.py
  mv blaze.py /usr/local/bin/blaze   # or ~/bin/ or any PATH folder

{Style.BOLD}TUI MODE:{Style.RESET}
  Use --tui for a live dashboard. rich is only imported when --tui is used.
  Install rich:  pip install rich

{Style.BOLD}CONFIG:{Style.RESET}  ~/.config/blaze/config.json
{Style.BOLD}SITES:{Style.RESET}   YouTube, SoundCloud, Bandcamp, Vimeo, Twitter/X, TikTok,
        Reddit, Instagram, Facebook, and 1000+ more.
"""
    )
    parser.add_argument("url", nargs="?", help="Video/playlist URL")
    parser.add_argument("-o", "--output", metavar="DIR", help="Output directory")
    parser.add_argument("-p", "--playlist", action="store_true", help="Download entire playlist")
    parser.add_argument("-i", "--input-file", metavar="FILE", help="Batch file (one URL per line)")
    parser.add_argument("-w", "--workers", type=int, metavar="N", help=f"Parallel workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--no-aria2c", action="store_true", help="Disable aria2c downloader")
    parser.add_argument("--tui", action="store_true", help="Launch rich TUI dashboard (pip install rich)")
    parser.add_argument("--check-update", action="store_true", help="Check for yt-dlp updates manually")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-error output")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--config", action="store_true", help="Open config file in default editor")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")
    return parser

def main():
    parser = create_parser()
    args = parser.parse_args()

    Logger.QUIET = args.quiet
    Logger.NO_COLOR = args.no_color or os.environ.get("NO_COLOR") or not sys.stdout.isatty()

    if args.check_update:
        Logger.banner()
        ytdlp_cmd, _ = DependencyInstaller.ensure_all()
        UpdateChecker.check_ytdlp(ytdlp_cmd)
        sys.exit(0)

    Logger.banner()

    config = Config.load()

    if args.config:
        config.save()
        editor = os.environ.get("EDITOR", "nano")
        Logger.info(f"Opening config: {CONFIG_FILE}")
        subprocess.call([editor, str(CONFIG_FILE)])
        return

    if args.output:
        config.output_dir = args.output
    if args.workers is not None:
        config.workers = args.workers
    if args.no_aria2c:
        config.use_aria2c = False

    config.save()

    # ═════════════════════════════════════════════════════════════════
    # AUTO-INSTALL DEPENDENCIES  (the magic sauce)
    # ═════════════════════════════════════════════════════════════════
    ytdlp_cmd, has_aria2c = DependencyInstaller.ensure_all()

    if has_aria2c:
        Logger.success("aria2c ready — ultra-fast mode enabled")
    else:
        Logger.warn("aria2c unavailable — using native downloader")

    urls = []
    if args.input_file:
        urls = URLParser.from_file(args.input_file)
    elif args.url:
        urls = [args.url]
    else:
        parser.print_help()
        sys.exit(1)

    engine = DownloadEngine(ytdlp_cmd, config, has_aria2c, tracker=None)
    output_dir = Path(config.output_dir).expanduser().resolve()

    if args.tui:
        success = run_tui(urls, output_dir, engine, config, playlist=args.playlist)
        if not success:
            if len(urls) == 1 and not args.playlist:
                engine.download(urls[0], output_dir, show_progress=True)
            elif len(urls) == 1 and args.playlist:
                engine.download(urls[0], output_dir, playlist=True, show_progress=True)
            else:
                engine.batch_parallel(urls, output_dir, config.workers, playlist=args.playlist)
    else:
        if len(urls) == 1 and not args.playlist:
            engine.download(urls[0], output_dir, show_progress=True)
        elif len(urls) == 1 and args.playlist:
            engine.download(urls[0], output_dir, playlist=True, show_progress=True)
        else:
            engine.batch_parallel(urls, output_dir, config.workers, playlist=args.playlist)

    if not args.tui or (args.tui and not success):
        print(f"\n{Style.CYAN}{'═'*60}{Style.RESET}")
        print(f"{Style.GREEN}{Style.BOLD}All operations complete.{Style.RESET} Files saved to: {output_dir}")
        print(f"{Style.CYAN}{'═'*60}{Style.RESET}\n")

if __name__ == "__main__":
    main()
