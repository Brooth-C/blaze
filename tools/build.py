#!/usr/bin/env python3
"""
Blaze Build Script — Cross-platform standalone executable builder
Usage: python tools/build.py

Builds a single-file executable that includes Python + Blaze + all logic.
Your friends don't need Python installed — just download and run.

Platform-specific binaries (build on each platform):
  - macOS (Intel):   build on Intel Mac → blaze-macos-x86_64
  - macOS (Apple S): build on M1/M2/M3 Mac → blaze-macos-arm64
  - Windows:         build on Windows → blaze.exe
  - Linux:           build on Linux → blaze-linux-x86_64
"""

import os
import sys
import shutil
import subprocess
import platform
import re
from pathlib import Path

APP_NAME = "blaze"
PROJECT_DIR = Path(__file__).resolve().parents[1]
VERSION = re.search(r'^VERSION = "([^"]+)"', (PROJECT_DIR / 'blaze.py').read_text(encoding='utf-8'), re.MULTILINE).group(1)


def get_output_name():
    """Generate platform-specific binary name."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        arch = "arm64" if "arm" in machine else "x86_64"
        return f"{APP_NAME}-macos-{arch}"
    elif system == "windows":
        return f"{APP_NAME}.exe"
    else:
        return f"{APP_NAME}-linux-{machine}"


def check_pyinstaller():
    """Ensure PyInstaller is available."""
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                       capture_output=True, check=True, timeout=10)
        return [sys.executable, "-m", "PyInstaller"]
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('Install PyInstaller, rich, mutagen and imageio-ffmpeg in your build environment first.') from exc


def build():
    output_name = get_output_name()
    print(f"\n{'='*60}")
    print(f"  Building Blaze v{VERSION}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Output:   {output_name}")
    print(f"{'='*60}\n")

    pyinstaller = check_pyinstaller()

    # Clean previous builds
    for folder in ["build", "dist"]:
        build_folder = PROJECT_DIR / folder
        if build_folder.exists():
            shutil.rmtree(build_folder)

    # Build command
    cmd = pyinstaller + [
        "--clean",
        "--noconfirm",
        str(PROJECT_DIR / "tools/blaze.spec")
    ]

    print(f"Running: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True, cwd=PROJECT_DIR)

    # Rename to platform-specific name
    src = PROJECT_DIR / "dist" / APP_NAME
    if sys.platform == "win32":
        src = src.with_suffix(".exe")

    dst = PROJECT_DIR / "dist" / output_name
    if sys.platform == "win32":
        dst = dst.with_suffix(".exe")

    if src != dst:
        shutil.move(str(src), str(dst))

    # Make executable on Unix
    if sys.platform != "win32":
        os.chmod(dst, 0o755)

    print(f"\n{'='*60}")
    print("  BUILD SUCCESSFUL!")
    print(f"  Binary: {dst.absolute()}")
    print(f"  Size:   {dst.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"{'='*60}\n")

    print("Python is bundled. First use still needs internet to obtain yt-dlp if it is unavailable.")
    print(f"\n  ./{output_name} \"https://youtube.com/watch?v=...\" --tui\n")


if __name__ == "__main__":
    build()

