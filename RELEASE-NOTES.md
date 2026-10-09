## Blaze 4.1.21

Download the Windows or Mac ZIP, extract it, then run Install-Blaze.bat or Install-Blaze.command. Rerun the newer installer to upgrade; existing downloads and settings are preserved.

### Interface
- Stable queue ordering, smoother progress bars and structured Unicode titles.
- Responsive paging and filters: N/P pages, F failed, A all, D active, Q or Ctrl+C stop.
- Layout adapts to small windows and terminal resizing; activity stays inside the dashboard.
- Less idle redrawing, clear waiting/conversion stages and readable failure summaries.
- Interactive audio format choices and remembered download type between downloads.

### Reliability
- Cancellation stops downloader children and retains partial files for resume.
- Optional tools no longer cause unnecessary first-launch download attempts; missing FFprobe is reported as optional.
- Invalid progress/config values cannot overflow the UI or create extreme worker counts.
- Installer upgrades validate new application code before replacing the installed app. Mac setup prevents concurrent installers.
- Reproducible packages are checked against the canonical application to prevent stale bundled code.

### Release checks
Publication requires regression and reliability tests plus real local HTTP downloads, FFmpeg conversion, audio/video batches, history recovery, HTTP error reporting and interrupted-download resume.

Windows x64 and both Apple Silicon and Intel macOS runners additionally install the actual ZIP, launch it from a path containing spaces, test successful upgrades and invalid-source rejection, then run the suites using the installed private Python and bundled FFmpeg. Source tests cover Python 3.10 and 3.13 on Linux.

These checks do not guarantee every external website or older OS version. Public-service extractors can change independently. Blaze remains a terminal dashboard; optional mpv, aria2c and FFprobe are not included. SHA256SUMS.txt verifies the exact attached installers.
