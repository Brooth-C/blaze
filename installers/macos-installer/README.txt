BLAZE FOR MAC — PRIVATE INSTALLER

1. Extract the entire ZIP.
2. Double-click Install-Blaze.command.
3. After installation, double-click ~/Blaze/Start-Blaze.command.

Supports Apple Silicon and Intel Macs. Internet is needed for setup.
Python, uv, Rich, other packages, FFmpeg, aria2c, cache and installer temp files are installed
under ~/Blaze. No Homebrew, sudo, shell-profile edits or system Python changes.

If macOS blocks the downloaded script, try Control-click > Open, then Open.
If Finder reports missing execution permission, open Terminal, type
  bash
followed by a space, drag Install-Blaze.command into Terminal and press Enter.

Existing settings/downloads are preserved. Run one installer at a time and
close Blaze before rerunning setup. Optional mpv and FFprobe are not bundled.
aria2c installs automatically and uses native AppleTLS and macOS system libraries.
Its pinned SHA-256 is verified before execution. Rich and aria2c must pass their
setup checks before the installer reports success.

To check/repair dependencies without opening the download menu:
  ~/Blaze/Start-Blaze.command --install-deps

Release publication requires actual installation and upgrade tests on Apple
Silicon and Intel macOS runners, followed by local download/conversion/resume
tests using this private runtime. This does not cover every older macOS version
or every public website. The installer uses uv 0.12.19 and verifies its archive's
published SHA-256 before execution. New app code is validated before replacement.

