# Blaze for Apple Silicon 0.10.0 — stem separation

Music Studio can separate the current recording into **vocals, drums, bass and
other instruments** with one bundled SCNet model. Separation runs locally, with
progress and cancellation, and produces WAV stems for playback and export.
The model is included in the app, so splitting does not require a separate model
download or an online service.

This is a simple four-stem workflow. It does not separate piano and guitar into
their own tracks. Output can contain leakage and artifacts; these are estimated
stems rather than recovered studio multitracks. SCNet is the selected model for
this build, not a claim of universal best separation quality.

The model is the checksum-pinned ONNX export from Demixr's SCNet v0.1.2 release,
derived from the official SCNet checkpoint. Original SCNet and export license
notices and provenance are retained in `music_studio/stem_models`. The existing
chord, beat and meter models are unchanged.

New Mac builds support **Apple Silicon (M1 and newer) only**. The final Intel
0.9.0 package remains available in its original release. Windows, Linux and
Android downloads are unchanged by this Mac build. The combined v4.5.0 Latest
distribution remains available separately; this Mac release has its own download.

The application retains its native sidebar, toolbar, persistent player and
macOS 26 system glass, with the existing system-material fallback on older Macs.
Download and provider access still need internet. Chord analysis and stem
separation run on the device. Transpose affects notation, not the recording's
pitch.

The app requires macOS 13 or newer. Extract the ZIP completely, then move
`Blaze.app` to Applications. No separate Python installation is required. This
build is ad-hoc signed and is not Apple-notarized; see the Mac setup guide for
first-launch instructions. The native build pipeline verifies the packaged app
on Apple Silicon macOS 15 and macOS 26, including actual local media processing.
Automated synthetic fixtures verify execution and file contracts, not separation
accuracy on every song or performance on every M-series Mac.
