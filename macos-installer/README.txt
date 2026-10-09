BLAZE FOR MAC — PRIVATE INSTALLER

1. Extract the entire ZIP.
2. Double-click Install-Blaze.command.
3. After installation, double-click ~/Blaze/Start-Blaze.command.

Supports Apple Silicon and Intel Macs. Internet is needed for setup.
Python, uv, packages, FFmpeg, cache and installer temp files are installed
under ~/Blaze. No Homebrew, sudo, shell-profile edits or system Python changes.

If macOS blocks the downloaded script, try Control-click > Open, then Open.
If Finder reports missing execution permission, open Terminal, type
  bash
followed by a space, drag Install-Blaze.command into Terminal and press Enter.

Existing settings/downloads are preserved. Run one installer at a time and
close Blaze before rerunning setup. Optional mpv, aria2c and FFprobe are not
bundled. Blaze uses native downloading and bundled FFmpeg.

The shell syntax and archive were checked on Linux. End-to-end installation
on macOS has not been tested here. The installer uses uv 0.12.19 and verifies
its archive's published SHA-256 before execution.
