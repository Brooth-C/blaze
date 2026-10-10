<div align="center">

<img src="docs/assets/blaze-logo.png" alt="Blaze flame and download logo" width="128">

# Blaze

**Audio and video downloads, with a live terminal dashboard.**

Windows · macOS · Linux · Android (Termux, experimental)

[![Quality checks](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml/badge.svg?branch=main)](https://github.com/Brooth-C/blaze/actions/workflows/quality-and-release.yml)

[Installation guide](docs/INSTALLATION.md) · [Usage guide](docs/USAGE.md) · [Get help](SUPPORT.md)

</div>

## Download and start

Choose your platform, extract the **entire ZIP**, then run its installer.
Setup needs internet access and installs Python for you.

| Platform | Download | Install | Launch after setup |
| --- | --- | --- | --- |
| Windows 10/11 (x64) | [Windows ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Windows-Installer.zip) | Double-click `Install-Blaze.bat` | `%USERPROFILE%\Blaze\Start-Blaze.bat` |
| macOS (Apple Silicon / Intel) | [macOS ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Mac-Installer.zip) | Double-click `Install-Blaze.command` | `~/Blaze/Start-Blaze.command` |
| Linux (x86_64 / ARM64, glibc) | [Linux ZIP](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Linux-Installer.zip) | `bash Install-Blaze.sh` | `bash ~/Blaze/Start-Blaze.sh` |

Android users: see the [Termux setup guide](docs/ANDROID.md). Android support is experimental and has not yet been verified on a physical device.

[Release notes and checksums](https://github.com/Brooth-C/blaze/releases/latest) · [Detailed setup and requirements](docs/INSTALLATION.md)

## Why Blaze

- **See every download.** Track progress, speed, ETA, conversion and merging in a keyboard-controlled terminal dashboard.
- **Pick audio or video.** Download through yt-dlp and choose your format and video quality.
- **Resume interrupted work.** Keep partial downloads and review job reports.
- **Keep everything together.** The private runtime, settings, reports and downloads live inside your Blaze folder.

## Using Blaze

Launch Blaze and follow the terminal prompts. Use **N / P** to page through the queue,
**F** to show failed downloads, **A** to show all, and **D** to show active and waiting jobs.
**Q / Ctrl+C** stops downloads and keeps partial files.

Prefer commands? With Python 3.10+ installed, run `python blaze.py --help`.
See the [usage guide](docs/USAGE.md) and [source setup](docs/INSTALLATION.md#run-from-source).

## Help and project information

[Troubleshooting](SUPPORT.md) · [Report a bug](https://github.com/Brooth-C/blaze/issues/new?template=bug_report.yml) · [Contributing](CONTRIBUTING.md) · [Tests and project structure](docs/DEVELOPMENT.md)

## Free to use

Copyright © 2026 Brooth-C. You may download, install and run Blaze for free,
including for commercial use, under the [Blaze Free-Use License](LICENSE.txt).
Brooth-C retains ownership; modification and redistribution require separate permission.
Third-party components retain their [own licenses](THIRD-PARTY-NOTICES.md).
