# Blaze desktop for Linux

The desktop installer targets Ubuntu 22.04 x86_64. It runs the same Explore, Downloads, Library and Music Studio workflow as Windows and Mac using GTK 3 and WebKitGTK 4.1. Models and Node are included; no account or model setup is needed. Installing Python dependencies requires internet access once. Local media playback and analysis then work offline; discovery and downloading remote media require internet.

1. Install system requirements: `sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-webkit2-4.1 ffmpeg`.
2. Extract `Blaze-Linux-x86_64.tar.gz`.
3. Run `sh Blaze/Install-Blaze.sh` from a terminal. The installer modifies only your user account and does not run sudo.
4. Open Blaze from the applications menu.

Explore starts with general music recommendations and offers song/video search
inside Blaze. Choose an item to prepare a local playback copy, then keep listening
while changing sections. Use Download for a permanent library copy or Open in
Studio for local chord analysis. The bounded playback cache is separate from
saved downloads. Recommendations use listening inside Blaze without a YouTube
login; search terms still reach the provider. Reset local listening history in
Explore to start over.

The app is installed into `~/.local/share/BlazeApp`; personal analysis data stays separately in `~/.local/share/Blaze`. Downloaded media goes to `~/Downloads/Blaze` by default. Close Blaze before updating and rerun the new installer. Remove `~/.local/share/BlazeApp` and `~/.local/share/applications/blaze.desktop` to uninstall; your downloaded files and analysis data are kept.

Other distributions, ARM Linux, Wayland-only configurations and older WebKit versions are not validated by this release. FFmpeg and GTK/WebKit remain system-provided dependencies, with their distribution's own licenses and sources. The existing terminal installer remains available separately.
