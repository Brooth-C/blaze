# Testing and project structure

[Back to Blaze](../README.md) | [Contribution guidelines](../CONTRIBUTING.md)

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
