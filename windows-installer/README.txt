BLAZE FOR WINDOWS — PRIVATE INSTALLER

1. Extract this entire ZIP to a normal folder.
2. Double-click Install-Blaze.bat. Internet access is required during setup.
3. When setup completes, open %USERPROFILE%\Blaze\Start-Blaze.bat.

Supports 64-bit x64 Windows 10/11. No Python installation or admin
rights are needed beforehand. Windows PowerShell 5.1 is used for setup.

Everything newly installed stays inside %USERPROFILE%\Blaze:
  App           Blaze program
  .runtime      managed Python, Rich/packages, uv, FFmpeg, aria2c, cache and temp
  Config        settings
  Audio/Video   downloaded media
  Reports       job results and logs

The installer uses uv 0.12.19, validates its archive's published SHA-256,
and installs managed Python 3.13 without registry registration or global
Python launchers. Neither system PATH nor machine execution policy is changed.
The BAT permits the included PowerShell script only for its setup process.

aria2c is installed automatically from its upstream portable x64 archive.
Its pinned SHA-256 is verified before execution. Rich and aria2c must pass their
setup checks before the installer reports success.
Automatic playback needs a separately supplied portable mpv.
FFprobe is optional and is not included. The bundled FFmpeg handles conversion.

To check/repair dependencies without opening the download menu:
  %USERPROFILE%\Blaze\Start-Blaze.bat --install-deps

To update the app: extract a newer package and rerun Install-Blaze.bat.
To remove this installation: close Blaze and delete its folder. Back up your
Audio, Video, Config and Reports first if you want to keep them.

Release publication requires actual installation and upgrade tests on an x64
Windows runner, followed by local download/conversion/resume tests using this
private runtime. This does not cover every Windows version or every public
website. New app code is validated before replacing the installed app.

