# Installation guide

[Back to Blaze](../README.md)

## Windows setup - no Python needed beforehand

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

## Mac setup - Apple Silicon and Intel

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

## Linux setup - x86_64 and ARM64

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
