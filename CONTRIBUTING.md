# Contributing to Blaze

Start with a focused issue or pull request explaining the problem and the intended result.

## Local setup

Use Python 3.10 or newer in an isolated development environment:

```sh
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux, or
`.venv\Scripts\Activate.ps1` in Windows PowerShell. Then:

```sh
python -m pip install rich yt-dlp mutagen imageio-ffmpeg ruff
python -m ruff check --select F,E9 blaze.py build.py package_installers.py Blaze-*-Tests.py
python Blaze-Regression-Tests.py
python Blaze-Reliability-Tests.py
python Blaze-Integration-Tests.py
```

The regression suite uses mocks and a locally generated wheel; it does not
require downloading media. The POSIX terminal tests are skipped on Windows.
The suites create a temporary Python environment, so Python's venv/ensurepip
support must be available. Integration tests also need FFmpeg on PATH; they
serve generated media on localhost and do not contact public download services.

## Project conventions

- Keep managed dependencies, configuration, and runtime state inside the Blaze installation folder.
- Preserve terminal behavior on Windows, macOS, and Linux.
- Avoid adding system package-manager installations, permanent PATH changes, or administrator requirements.
- Keep Spotify/spotDL support removed.
- Add regression coverage for meaningful behavior changes.
- Explain which checks passed and which platforms were actually tested.
- Never commit credentials, cookies, personal media, or unredacted downloader logs.

## Installer changes

The application also exists in all three installer source folders. When changing
`blaze.py`, run `python package_installers.py` to synchronize those copies and
rebuild the downloadable ZIPs. Run `python package_installers.py --check` to
detect stale source or package contents. Verify archive contents and script syntax. Do not claim end-to-end Windows or
macOS or Linux validation unless the installer was actually run on that platform.
The quality workflow checks source behavior on Python 3.10/3.13 and installs
the ZIPs on Windows x64, Apple Silicon macOS Intel macOS, Ubuntu x86_64 and Ubuntu ARM64 runners. It checks
upgrades and runs download suites with the installed private runtime. Automatic
publication runs only after all checks pass, and never replaces an existing
version's release assets. Increment VERSION and update RELEASE-NOTES.md for a
new release. Run Blaze-Installer-Tests.py only on a disposable clean runner.

## Pull requests

Describe the concrete problem, resulting behavior, and validation.
Keep unrelated changes separate. Discuss new dependencies before introducing them.

## License

This repository currently has no project license. Contributions do not establish
a new license; licensing decisions belong to the repository owner.
