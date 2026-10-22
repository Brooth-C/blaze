<div align="center">

<img src="docs/assets/blaze-logo.png" alt="Blaze flame and download logo" width="112">

# Blaze

**Download audio and video on your desktop or phone.**

Windows · macOS · Linux · Android

[Download Blaze](https://github.com/Brooth-C/blaze/releases/latest) · [Guides](docs/README.md) · [Get help](SUPPORT.md)

[![Quality checks](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml/badge.svg?branch=main)](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml)

</div>

## Get Blaze

| Platform | Download |
| --- | --- |
| Windows 10/11 · x64, 0.8.0 | [Blaze Windows app](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Windows.zip) |
| macOS 13+ · Apple Silicon, 0.8.0 preview | [Blaze Mac app](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-arm64.zip) |
| macOS 13+ · Intel, 0.8.0 preview | [Blaze Mac app](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-x86_64.zip) |
| Linux desktop · Ubuntu 22.04 x86_64, 0.8.0 preview | [Blaze Linux desktop](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Linux-x86_64.tar.gz) |
| Linux terminal · x86_64 / ARM64, glibc | [Linux ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Linux-Installer.zip) |
| Android 7+ · ARM64, 0.11.0 | [Android APK](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Android-Preview.apk) |

Blaze 4.4.0 Latest includes desktop 0.8.0 and the tested Android 0.11.0 APK.

Download one file for your platform using the links above. For Windows, extract
the ZIP and run Blaze.exe. On Mac, extract the ZIP and move Blaze.app to Applications. Tap the Android APK to install. Linux and Termux installer setup needs an internet connection; follow the matching guide.
Linux desktop uses a tar.gz installer and system Python, GTK/WebKit and FFmpeg; see the [Linux guide](docs/LINUX-DESKTOP.md). Windows requires Microsoft Edge WebView2 Runtime.
Mac previews are ad-hoc signed without Apple notarization; see the [macOS guide](docs/MACOS.md) for first launch.
[Detailed installation](docs/INSTALLATION.md) · [Checksums and release files](https://github.com/Brooth-C/blaze/releases/latest)

Prefer a terminal on Android? Download the [Termux ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Termux-Installer.zip) and follow the [Termux guide](docs/ANDROID.md).

## What you can do

- Find songs and videos inside Explore, then play or download them.
- Get music recommendations from listening inside Blaze, without YouTube login.
- Download audio or video and choose quality and format.
- Track downloads, keep a queue and resume supported partial files.
- Convert audio and merge separate video/audio streams.
- Keep downloads on your device and open or export completed files.

The Windows, Mac and Linux desktop apps bring Android's Explore → listen →
download → Library/Studio workflow to a desktop sidebar. A persistent player
keeps the current media across sections. Selecting an online result first
prepares a local playback copy with progress and cancellation; Download keeps a
permanent library copy. Saved appearance, library search and offline chord
analysis remain available. See the [desktop 0.8.0 notes](docs/RELEASE-0.8.0.md).

The Mac build trials native Liquid Glass navigation on macOS 26 with an older
system fallback. Discovery needs internet; local analysis stays on the device.

[Windows player and build guide](music_studio/README.md).
The Linux and Termux terminal installers retain the keyboard-controlled dashboard. The previous Mac terminal installer remains in v4.1.29.
The [Windows terminal installer](https://github.com/Brooth-C/blaze/releases/download/v4.1.29/Blaze-Windows-Installer.zip) remains available.
The [Android app](docs/ANDROID-APK.md) has a built-in audio/video player, touch controls, history, playlists and
MP3/M4A/WAV/FLAC conversion. It is debug-signed; physical-phone testing
is still needed.
Android 0.11.0 improves video search and Studio playback while keeping the existing
interface. Search updates after a short typing pause, and All includes ordinary
YouTube videos. Studio video preview and fullscreen keep the same playback session.
Explore retains music recommendations personalized from listening inside Blaze,
without YouTube login, alongside Now Playing, Download and offline Studio. The same tested APK
is included with the desktop downloads in the main [Latest release](https://github.com/Brooth-C/blaze/releases/latest).
Native screenshots remain available in its [Android release](https://github.com/Brooth-C/blaze/releases/tag/android-v0.11.0).

## Find your way

[Installation](docs/INSTALLATION.md) · [Desktop usage](docs/USAGE.md) · [Android app](docs/ANDROID-APK.md) · [Troubleshooting](SUPPORT.md)

[Report a bug](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml) · [Request a feature](https://github.com/Brooth-C/blaze/issues/new?template=feature_request.yml) · [Development](docs/DEVELOPMENT.md) · [Contributing](CONTRIBUTING.md)

## Ownership and free use

© 2026 Brooth-C. Free to download, install and run, including commercially,
under the [Blaze Free-Use License](LICENSE.txt). Brooth-C retains ownership;
modification and redistribution require permission. Third-party software keeps
its [own licenses](THIRD-PARTY-NOTICES.md).

