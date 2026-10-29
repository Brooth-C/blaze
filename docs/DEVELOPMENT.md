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
python tests/Blaze-Mobile-Integration-Tests.py
python tools/package_installers.py --check
```

Installer sources are in `installers/windows-installer/`, `installers/macos-installer/`, `installers/linux-installer/` and `installers/termux-installer/`. Download only media you are
permitted to download.

## Project map

User guides are indexed in [the documentation hub](README.md).
The main release is a catalog of independently versioned platform builds.
`tools/release_catalog.json` pins the original tags, sizes and SHA256 digests;
`tools/release_page.py` verifies and mirrors only missing install downloads.
Main CI maintains the catalog notes without changing its Latest state or
replacing published files. Publish a new catalog tag explicitly when collecting
new validated platform builds. Source and license archives remain linked from
immutable original releases; normal users need only their platform's install file.

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
uses JDK 17, Python 3.12 and Android SDK 36. It stages checksum-verified native
FFmpeg/LAME, QuickJS, LibVLC and model assets for ARM64/x86_64, checks backend and fixture media,
runs lint and Android 10/15 instrumented queue/runtime/media tests, and captures
the foreground app. See [android/README.md](../android/README.md).
Main builds publish immutable versioned Android prereleases after these checks;
pull requests produce temporary artifacts. Physical-phone testing and broad
public-service compatibility remain outstanding.

## Desktop packages and distribution

The [Windows/Linux workflow](https://github.com/Brooth-C/blaze/actions/workflows/desktop-release.yml)
freezes the Windows app and packages the Linux GTK installer. It installs and runs the actual packages,
checks real model inference and edits/exports, then exercises local downloading, native playback,
seeking and layout. Linux desktop targets Ubuntu 22.04 x86_64 with system GTK/WebKit and FFmpeg.
The [Mac workflow](https://github.com/Brooth-C/blaze/actions/workflows/macos-app.yml) builds Apple Silicon
and tests on macOS 26 only, including decoder formats and the rendered Cocoa interface.
Main-branch native gates publish new immutable platform releases; PRs retain artifacts and screenshots.
After both Mac jobs pass on main, the Mac publisher creates a normal stable release
and marks it Latest. Existing source and asset hashes must match before a release's
Latest metadata may be promoted; other platform binaries are preserved.

The [distribution workflow](https://github.com/Brooth-C/blaze/actions/workflows/distribution-release.yml)
uses `tools/release_catalog.json` to bring the independently versioned packages together.
`tools/promote_distribution.py` requires successful main-branch native runs, unchanged application,
packaging and license inputs, matching release targets, and exact asset sizes and SHA256 hashes.
It downloads and hashes each original binary before publishing a complete draft as GitHub Latest.
It preserves old releases and refuses differing existing assets. The distribution version is separate
from the terminal engine's version. `macos-promote.yml` is retained only as the manual historical
0.6 promotion workflow; new distributions use the general publisher.

