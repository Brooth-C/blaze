# Blaze

Blaze 4.1.20 is a terminal audio/video downloader with a responsive dashboard,
queue paging, per-download ETA, conversion/merging stages, resume support and
job reports. Spotify/spotDL support has been removed.

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
