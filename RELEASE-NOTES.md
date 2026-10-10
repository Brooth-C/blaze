## Blaze 4.1.23

The Windows and Mac installers now install aria2c automatically inside Blaze,
alongside Rich, Python, yt-dlp, Mutagen and FFmpeg. Close Blaze, extract the new
ZIP and rerun its installer. Settings, existing downloads and reports are preserved.

- Native Apple Silicon and Intel aria2 builds use AppleTLS and macOS system
  libraries. No Homebrew, admin access or system package installations are needed.
- Windows uses the upstream portable x64 aria2 archive. Every aria2 download
  must match its pinned SHA-256 before extraction or execution.
- Setup checks aria2c and Rich before reporting success. An unavailable requested
  dependency stops setup before replacing the installed app.
- Startup can restore missing aria2c. `--no-aria2c` opts out; `--install-deps`
  checks/repairs dependencies without opening the download menu.
- Fixed the downloader protocol rule so HTTP and HTTPS transfers actually use
  aria2c when enabled, instead of silently falling back to native downloading.
- Working private aria2 binaries are reused during upgrades. Failed downloads,
  mismatched checksums or unusable replacements preserve the existing binary.

Release checks include actual ZIP installation, upgrades and Rich rendering on
Windows x64, Apple Silicon macOS and Intel macOS. They verify aria2 HTTPS downloads
using the OS trust store and real audio conversion/video downloads through Blaze.
Source regression, UI, cancellation, history and native resume tests also run.

Blaze remains a terminal dashboard. Optional mpv and FFprobe are not bundled.
Public website extractors and every older OS version are not covered by these
checks. SHA256SUMS.txt verifies the exact attached installers.
