<div align="center">

# 🔥 Blaze

**Audio and video downloads. A live terminal dashboard. One private installation folder.**

[Download for Windows](https://github.com/Brooth-C/blaze/raw/refs/heads/main/downloads/Blaze-Windows-Installer.zip) · [Download for macOS](https://github.com/Brooth-C/blaze/raw/refs/heads/main/downloads/Blaze-Mac-Installer.zip) · [Report a bug](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml)

**4.1.20** · Windows 10/11 x64 · macOS Apple Silicon / Intel · Python 3.10+ from source

</div>

---

## What Blaze does

- Downloads audio or video through yt-dlp.
- Shows progress, speed, ETA, and conversion or merging stages.
- Handles download queues with paging and a failed-job filter.
- Supports resuming interrupted downloads and produces job reports.
- Keeps its managed runtime, settings, and downloads inside your Blaze folder.

Blaze uses a keyboard-controlled **terminal dashboard**. Spotify/spotDL support has been removed.

> **Start here:** use the Windows or macOS installer links above for the current
> 4.1.20 packages. The older v4.0.0 GitHub release has no installer attachments.
> Setup requires internet access; Python does not need to be installed beforehand.

## Windows setup — no Python needed beforehand

**[Download the Windows installer ZIP](https://github.com/Brooth-C/blaze/raw/refs/heads/main/downloads/Blaze-Windows-Installer.zip)**

1. Extract the entire ZIP.
2. Double-click `Install-Blaze.bat`. Internet is required during setup.
3. Run `%USERPROFILE%\Blaze\Start-Blaze.bat` after setup completes.

The package targets **x64 Windows 10/11**. It installs managed Python 3.13,
yt-dlp, Rich, Mutagen and bundled FFmpeg privately using uv 0.12.19.
It verifies the uv archive against its published SHA-256 before executing it.
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

Existing installations elsewhere are left untouched. Optional mpv, aria2c and
FFprobe are not bundled; native downloading and bundled FFmpeg are used.

## Mac setup — Apple Silicon and Intel

**[Download the Mac installer ZIP](https://github.com/Brooth-C/blaze/raw/refs/heads/main/downloads/Blaze-Mac-Installer.zip)**

1. Extract the entire ZIP.
2. Double-click `Install-Blaze.command`. Internet is required during setup.
3. Double-click `~/Blaze/Start-Blaze.command` after setup completes.

Python, dependencies and bundled FFmpeg install privately under `~/Blaze`.
No Homebrew, administrator access or shell-profile edits are required.
If macOS blocks opening the script, Control-click it and choose Open. See the
included README for the Terminal fallback.

## Run from source

Requires an existing Python 3.10+ interpreter:

```sh
python blaze.py
python blaze.py --mode audio -F mp3 "https://example.org/audio"
python blaze.py --mode video --video-resolution 1080p "https://example.org/video"
python blaze.py --help
```

Missing Python packages are installed into `~/Blaze/.runtime/venv`.
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
| Ctrl+C | Stop downloads and keep partial files |

Use `--no-tui` for plain terminal output and `--no-aria2c` for native downloading.
Output history is scoped to format/quality and destination. Different media
jobs writing to the same folder are serialized to prevent overlapping writes.
Playlist reports describe the URL job result, not a per-track completeness audit.

## Validation

28 regression tests passed on Linux, including actual Rich rendering at five
terminal sizes, POSIX pseudoterminal input/restoration and a real offline
private-environment installation. Python compilation and CLI help passed.
The Windows installer was statically checked but has **not** been run end to end
on Windows. The Mac script passed shell syntax and ZIP integrity checks, but
has **not** been run end to end on macOS. Live public-service downloads were not tested in this revision.

Run the tests in a Python environment with Rich installed:

```sh
python Blaze-Regression-Tests.py
```

Installer sources are in `windows-installer/` and `macos-installer/`. Download only media you are
permitted to download.

## Help and contributions

Found a problem? [Open a bug report](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml) with your platform, Blaze version, steps, and sanitized error output.
For changes to the project, read [CONTRIBUTING.md](CONTRIBUTING.md).

## Project map

| Path | Purpose |
| --- | --- |
| `blaze.py` | Main application |
| `Blaze-Regression-Tests.py` | Offline regression suite |
| `windows-installer/` | Windows installer sources |
| `macos-installer/` | macOS installer sources |
| `downloads/` | Ready-to-download installer ZIPs |
| `build.py`, `blaze.spec` | Legacy standalone build tools |

No project license has been added yet. Public source availability alone does not grant a general license to redistribute or modify it.
