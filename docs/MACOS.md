# Blaze for macOS

Blaze includes Downloads, Music Studio and Library in one native macOS app.
Music Studio uses the same advanced offline chord ensemble and beat/meter engine
as the Windows release. Its models and decoder are bundled; no Python, Homebrew
or model installation is required to use the app.

## Install

Open [Download for Mac](https://brooth-c.github.io/blaze/mac/). It automatically
selects the ZIP when your browser exposes the processor. If detection is unavailable,
choose the chip shown in Apple menu → About This Mac. One download button handles
both Mac processors. Direct ZIPs remain available in the Mac release for fallback:

- **Blaze-Mac-arm64.zip** for Apple Silicon (M1 and newer).
- **Blaze-Mac-x86_64.zip** for Intel Macs.

Requires macOS 13 or newer. Extract the ZIP completely, then move **Blaze.app**
to Applications. The app name is **Blaze**. Music Studio is a section inside it.

This preview is ad-hoc signed, without an Apple Developer ID or notarization.
macOS may ask you to allow the first launch through System Settings → Privacy
& Security → Open Anyway. Do not turn off Gatekeeper globally.

Open Downloads to paste a link and choose audio/video and format. Open Music
Studio to import a local audio/video file, analyse it, then play along with the
chord timeline and piano/guitar voicings. Advanced chord analysis is the default.
Video playback depends on the system web view's supported codecs; the bundled
decoder can analyse additional formats even when the preview cannot play them.
YouTube and other sites can independently require authentication or reject a
download. This is not removed by the offline chord engine.

Settings and saved analyses live in `~/Library/Application Support/Blaze`.
Downloads default to `~/Downloads/Blaze`. Updating the app bundle preserves them.

## Rebuild and third-party materials

The `.github/workflows/macos-app.yml` workflow builds and tests native Apple
Silicon and Intel packages separately. Models are copied from the checksum-pinned
Windows release, not retrained. `tools/stage_macos_studio.py` pins Node 22.20.0
and builds the plain yt-dlp 2026.8.19 plus EJS 0.8.0 downloader, excluding optional GPL libraries. The build uses Python 3.12.10, PyInstaller 6.16.0,
pywebview 6.1, NumPy 1.26.4 and ONNX Runtime 1.20.1.

`tools/macos_decoder` builds FFmpeg 7.1.3 with LGPL-compatible options and exact
LAME/Ogg/Vorbis/Opus sources. GPL, nonfree and version3 components are disabled.
FFmpeg and FFprobe run as separate, independently replaceable executables.
Corresponding decoder sources, recipe, configuration and licenses are included
in the app's `Contents/Resources/licenses` folder. Source, model and dependency
notices retain their original licenses and are not covered by Blaze's own license.

CI checks the packaged app's native signature, architecture, audio conversions,
4K media decoding, local downloads, offline ensemble, edits/exports, Cocoa launch,
playback/seeking and layout. Mock tests alone do not establish native behavior,
and these checks do not establish annotated real-song chord accuracy.

The earlier [Mac terminal installer](https://github.com/Brooth-C/blaze/releases/download/v4.1.29/Blaze-Mac-Installer.zip)
remains available separately.
