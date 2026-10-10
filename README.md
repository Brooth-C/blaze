<div align="center">

# ðŸ”¥ Blaze

**Audio and video downloads. A live terminal dashboard. One private installation folder.**

[![Quality checks](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml/badge.svg?branch=main)](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml)

[Download for Windows](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Windows-Installer.zip) Â· [Download for macOS](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-Installer.zip) Â· [Download for Linux](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Linux-Installer.zip) Â· [Report a bug](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml)

**4.1.24** Â· Windows 10/11 x64 Â· macOS Apple Silicon / Intel Â· Linux x86_64 / ARM64 (glibc) Â· Python 3.10+ from source

</div>

---

## What Blaze does

- Downloads audio or video through yt-dlp.
- Shows progress, speed, ETA, and conversion or merging stages.
- Keeps queue rows stable, with paging, active/failed filters and responsive keyboard controls.
- Adapts to terminal resizing and small windows, with bounded redraws and smooth progress bars.
- Supports resuming interrupted downloads and produces job reports.
- Keeps its managed runtime, settings, and downloads inside your Blaze folder.

Blaze uses a keyboard-controlled **terminal dashboard**. Spotify/spotDL support has been removed.

> **Start here:** download the Windows, macOS or Linux installer from the
> [v4.1.24 release](https://github.com/Brooth-C/blaze/releases/tag/v4.1.24).
> All three installers and SHA-256 checksums are attached to the release.
> Setup requires internet access; Python does not need to be installed beforehand.

## Windows setup â€” no Python needed beforehand

**[Download the Windows installer ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Windows-Installer.zip)**

1. Extract the entire ZIP.
2. Double-click `Install-Blaze.bat`. Internet is required during setup.
3. Run `%USERPROFILE%\Blaze\Start-Blaze.bat` after setup completes.

The package targets **x64 Windows 10/11**. It installs managed Python 3.13,
yt-dlp, Rich, Mutagen, bundled FFmpeg and portable aria2c privately using uv 0.12.19.
It verifies downloaded uv and aria2 archives using SHA-256 before execution.
No administrator access, permanent PATH edits, registry registration or system
package-manager installation is requested.

New installed files stay inside `%USERPROFILE%\Blaze`:

| Folder | Contents |
| --- | --- |
| `.runtime` | Private Python, packages, tools, cache and installer temp files |
| `App` | Blaze program |
| `Config` | Settings |
| `Audio`, `Video` | Downloads |
| `Reports` | Job results and downloader logs |

Existing installations elsewhere are left untouched. Optional mpv and FFprobe
are not bundled. aria2c is installed automatically; use `--no-aria2c` to opt out.

## Mac setup â€” Apple Silicon and Intel

**[Download the Mac installer ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-Installer.zip)**

1. Extract the entire ZIP.
2. Double-click `Install-Blaze.command`. Internet is required during setup.
3. Double-click `~/Blaze/Start-Blaze.command` after setup completes.

Python, Rich, the other dependencies, bundled FFmpeg and aria2c install privately under `~/Blaze`.
The Mac aria2 binaries are built from upstream 1.37.0 with native AppleTLS and
macOS system libraries, and their SHA-256 hashes are checked before execution.
No Homebrew, administrator access or shell-profile edits are required.
If macOS blocks opening the script, Control-click it and choose Open. See the
included README for the Terminal fallback.

For updates, close Blaze and rerun the newer installer. Setup checks the new
program before replacing the installed app and preserves settings and downloads.
Setup verifies that Rich imports and aria2c runs before reporting success.

## Linux setup â€” x86_64 and ARM64

**[Download the Linux installer ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Linux-Installer.zip)**

1. Extract the entire ZIP and open a terminal in the extracted folder.
2. Run `bash Install-Blaze.sh` with internet access.
3. Run `bash ~/Blaze/Start-Blaze.sh` after setup completes.

Requires glibc Linux, Bash, curl, tar, sha256sum, awk and mktemp.
Alpine/musl and 32-bit systems are not supported by this installer.
Python 3.13, dependencies, FFmpeg and aria2c install privately under `~/Blaze`.
No sudo or shell-profile edits are required. Close Blaze and rerun the newer
installer to upgrade while preserving settings and downloads.

## Run from source

Requires an existing Python 3.10+ interpreter:

```sh
python blaze.py
python blaze.py --mode audio -F mp3 "https://example.org/audio"
python blaze.py --mode video --video-resolution 1080p "https://example.org/video"
python blaze.py --help
python blaze.py --install-deps
```

Missing Python packages are installed into `~/Blaze/.runtime/venv`.
Missing aria2c installs automatically into `~/Blaze/.runtime/bin` on supported
64-bit Mac, Windows and Linux platforms. `--install-deps` checks/repairs dependencies
without opening the download menu. A failed installer dependency check stops setup.
Automatic system installers are disabled. Old configuration is read as a
fallback and settings are saved under `~/Blaze/Config`.
The legacy `build.py` / `blaze.spec` files are developer build tools, not the
recommended private installation path.

## Dashboard controls

| Key | Action |
| --- | --- |
| N / P | Next / previous queue page |
| F | Failed downloads only |
| A | All downloads |
| D | Active and waiting downloads |
| Q / Ctrl+C | Stop downloads and keep partial files |

Use `--no-tui` for plain terminal output and `--no-aria2c` for native downloading.
Output history is scoped to format/quality and destination. Different media
jobs writing to the same folder are serialized to prevent overlapping writes.
Playlist reports describe the URL job result, not a per-track completeness audit.

## Validation

The [quality workflow](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml)
gates release publication on source checks with Python 3.10/3.13 and actual ZIP
installation on Windows x64, Apple Silicon macOS Intel macOS, Ubuntu x86_64 and Ubuntu ARM64 runners.

The application tests cover regression cases, terminal rendering across
216 size/filter combinations, keyboard restoration, cancellation, config
recovery and private dependency installation. Real local HTTP fixtures test
FFmpeg conversion, mixed audio/video downloads, history recovery, HTTP errors
and resuming a cancelled download. Installer tests also check paths containing
spaces, successful upgrades, preservation of user files and invalid-source rejection.
They require private aria2c, verify Rich rendering and HTTPS downloads, reject
non-system Mac libraries, and exercise actual audio/video downloads through aria2c.

Public-service downloads and every older OS version are not covered. Website
extractors can change independently; passing tests is not a promise of zero bugs.

Run the tests in a Python environment with Rich, yt-dlp and FFmpeg available:

```sh
python Blaze-Regression-Tests.py
python Blaze-Reliability-Tests.py
python Blaze-Integration-Tests.py
python package_installers.py --check
```

Installer sources are in `windows-installer/`, `macos-installer/` and `linux-installer/`. Download only media you are
permitted to download.

## Help and contributions

Found a problem? [Open a bug report](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml) with your platform, Blaze version, steps, and sanitized error output.
For troubleshooting, read [SUPPORT.md](SUPPORT.md). For changes to the project, read [CONTRIBUTING.md](CONTRIBUTING.md).

## Project map

| Path | Purpose |
| --- | --- |
| `blaze.py` | Main application |
| `Blaze-Regression-Tests.py` | Offline regression suite |
| `Blaze-Reliability-Tests.py` | UI, cancellation, configuration and subprocess checks |
| `Blaze-Integration-Tests.py` | Real downloads from a local HTTP server |
| `Blaze-Installer-Tests.py` | Install/upgrade checks for disposable platform runners |
| `package_installers.py` | Rebuild/check packages from the canonical source |
| `windows-installer/` | Windows installer sources |
| `macos-installer/` | macOS installer sources |
| `linux-installer/` | Linux installer sources |
| `downloads/` | Ready-to-download installer ZIPs |
| `build.py`, `blaze.spec` | Legacy standalone build tools |

No project license has been added yet. Public source availability alone does not grant a general license to redistribute or modify it.

