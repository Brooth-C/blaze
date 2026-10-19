# Blaze 0.7.0 — a clearer desktop experience

Downloads, Library and Music Studio now share a quieter interface, clearer typography, immediate control feedback and System / Light / Dark appearances. Appearance is saved locally and survives restarts.

- Add links and choose Audio or Video; playlist options live under More options.
- Search and filter the local Library, then open a file in Studio.
- Import and analyze from the Studio header; drag the waveform to seek continuously.
- Use keyboard shortcuts and enlarged text without losing access to controls.
- Android's home screen follows system appearance with clearer Downloads / History / Library selection.
- Linux now has a GTK desktop installer for Ubuntu 22.04 x86_64, alongside the existing terminal installer.

The pretrained recognition models and reviewed native decoder assets are unchanged. Downloading remote media needs internet; chord analysis runs on the device without an account or remote inference service. Quality and available formats depend on the original media. Some video containers can be analyzed but cannot play in a platform webview.

Windows needs Microsoft Edge WebView2. Mac requires macOS 13+ and is ad-hoc signed, not Apple-notarized; first launch may need Privacy & Security → Open Anyway. Android remains a debug-signed preview. Linux installation needs the documented system renderer, FFmpeg and one-time internet access for Python dependencies. Platform workflow receipts and screenshots accompany the build artifacts.

Previous published binaries remain available under their original release tags. Checksums identify the exact new assets. No third-party account connections, automated agent hooks or paid services are configured by this release.
