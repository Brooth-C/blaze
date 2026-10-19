# Blaze desktop for Linux

The desktop installer is tested on Ubuntu 22.04 x86_64. It runs the same local Downloads, Library and Music Studio interface as Windows and Mac using GTK 3 and WebKitGTK 4.1. Models and Node are included; no account or model setup is needed. Installing Python dependencies requires internet access once. Downloads and analysis run locally afterward; downloading remote media requires internet.

1. Install system requirements: `sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-webkit2-4.1 ffmpeg`.
2. Extract `Blaze-Linux-x86_64.tar.gz`.
3. Run `sh Blaze/Install-Blaze.sh` from a terminal. The installer modifies only your user account and does not run sudo.
4. Open Blaze from the applications menu.

The app is installed into `~/.local/share/BlazeApp`; personal analysis data stays separately in `~/.local/share/Blaze`. Downloaded media goes to `~/Downloads/Blaze` by default. Close Blaze before updating and rerun the new installer. Remove `~/.local/share/BlazeApp` and `~/.local/share/applications/blaze.desktop` to uninstall; your downloaded files and analysis data are kept.

Other distributions, ARM Linux, Wayland-only configurations and older WebKit versions are not validated by this release. FFmpeg and GTK/WebKit remain system-provided dependencies, with their distribution's own licenses and sources. The existing terminal installer remains available separately.
