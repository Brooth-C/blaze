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
python tests/Blaze-Regression-Tests.py
python tests/Blaze-Reliability-Tests.py
python tests/Blaze-Integration-Tests.py
python tests/Blaze-Termux-Tests.py
python tests/Blaze-Mobile-Tests.py
python tools/package_installers.py --check
```

Installer sources are in `installers/windows-installer/`, `installers/macos-installer/`, `installers/linux-installer/` and `installers/termux-installer/`. Download only media you are
permitted to download.

## Project map

| Path | Purpose |
| --- | --- |
| `blaze.py` | Main application |
| `tests/Blaze-Regression-Tests.py` | Offline regression suite |
| `tests/Blaze-Reliability-Tests.py` | UI, cancellation, configuration and subprocess checks |
| `tests/Blaze-Integration-Tests.py` | Real downloads from a local HTTP server |
| `tests/Blaze-Installer-Tests.py` | Install/upgrade checks for disposable platform runners |
| `tools/package_installers.py` | Rebuild/check packages from the canonical source |
| `installers/windows-installer/` | Windows installer sources |
| `installers/macos-installer/` | macOS installer sources |
| `installers/linux-installer/` | Linux installer sources |
| `installers/termux-installer/` | Experimental Android / Termux installer |
| `android/` | Native Android APK preview and embedded downloader |
| `tests/Blaze-Termux-Tests.py` | Android dependency selection and packaging safety |
| `tests/Blaze-Mobile-Tests.py` | APK backend URL, playlist, format and cancellation safety |
| `downloads/` | Ready-to-download installer ZIPs |
| `tools/build.py`, `tools/blaze.spec` | Legacy standalone build tools |

## Android APK checks

The [APK workflow](https://github.com/Brooth-C/blaze/actions/workflows/android-apk.yml)
uses JDK 17, Python 3.12 and Android SDK 35. It runs backend tests, Android lint,
APK compilation, Android 10 emulator startup and embedded-runtime checks, and
captures the foreground app. See [android/README.md](../android/README.md).
Main builds publish immutable versioned Android prereleases after these checks;
pull requests produce temporary artifacts. Physical-phone testing and broad
public-service compatibility remain outstanding.
