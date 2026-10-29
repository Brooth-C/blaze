# Blaze for macOS

Blaze includes Explore, Downloads, Library and Music Studio in one macOS app.
Music Studio uses the same advanced offline chord ensemble and beat/meter engine
as the Windows release. Its models and decoder are bundled; no Python, Homebrew
or model installation is required to use the app.

## Install

Download **Blaze-Mac-arm64.zip** from the [Apple Silicon 0.15.0 release](https://github.com/Brooth-C/blaze/releases/tag/macos-v0.15.0). New development targets M1 and newer Macs only.

Intel users can keep using the final [0.9.0 Intel build](https://github.com/Brooth-C/blaze/releases/download/macos-v0.9.0-preview/Blaze-Mac-x86_64.zip); no new Intel builds are produced.

The bundle declares macOS 13 or newer; this release is validated on macOS 26 only.
Extract the ZIP completely, then move **Blaze.app**
to Applications. The app name is **Blaze**. Music Studio is a section inside it.

This build is ad-hoc signed, without an Apple Developer ID or notarization.
macOS may ask you to allow the first launch through System Settings → Privacy
& Security → Open Anyway. Do not turn off Gatekeeper globally.

Explore offers music recommendations and search inside Blaze. Choose a song or
video to prepare a local playback copy, with progress and cancellation. The same
player continues between sections. Use Download for a saved library copy or Open
in Studio to analyse the selected media. Recommendations use local listening
history without a YouTube login; requests still send search terms to the provider.
Reset the listening profile in Explore to start over.

Downloads also accepts pasted links and format choices. Open Music Studio to
import a local audio/video file, analyse it, then play along with the
chord timeline and piano/guitar voicings. Advanced chord analysis is the default.
Video playback depends on the system web view's supported codecs; the bundled
decoder can analyse additional formats even when the preview cannot play them.
YouTube and other sites can independently require authentication or reject a
download. This is not removed by the offline chord engine.

The native Mac navigation surface trials Liquid Glass on macOS 26, with an older
system material fallback. The shared content and Studio timeline retain readable
surfaces. Native glass is limited to the Mac chrome rather than applied to every
card or chord cell.

Settings, listening history, playback cache and saved analyses live in `~/Library/Application Support/Blaze`.
Downloads default to `~/Downloads/Blaze`. Updating the app bundle preserves them.

## Separate a recording

Open a song or video in Music Studio, then choose **Split stems → Nine stems**.
Blaze exports vocals, drums, bass, piano, guitar, strings, brass, synths and other.
The existing BS-RoFormer and piano stages create the main tracks; a new local
instrument model refines Other. **Five stems** retains the shorter workflow
where guitar, strings, brass and synths stay together in Other. Progress and
cancellation remain available; each completed track can be played or exported.
Nine stems takes substantially longer than five, with the larger model bundled.
 Separation can leave leakage or
artifacts and does not reproduce the original studio session.

The separation model is separate from the chord-recognition models. Its pinned
ONNX file, source references and original MIT notices are retained inside
`Blaze.app/Contents/Resources/music_studio/stem_models`.

## Rebuild and third-party materials

The `.github/workflows/macos-app.yml` workflow builds Apple Silicon only and
tests the packaged app on macOS 26 only. Chord-analysis models are copied
from the checksum-pinned Windows release, not retrained. The BS-RoFormer, Spleeter piano and selected Mega instrument heads are separately
staged from checksum-pinned exports. The legacy four-stem SCNet API remains for compatibility.
`tools/stage_macos_studio.py` pins Node 22.20.0
and builds the plain yt-dlp 2026.8.19 plus EJS 0.8.0 downloader, excluding optional GPL libraries. The build uses Python 3.12.10, PyInstaller 6.16.0,
pywebview 6.1, NumPy 1.26.4 and ONNX Runtime 1.20.1. The Cocoa bridge is isolated
from the shared interface and guards newer native classes at runtime.

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

## Piano isolation

Open a recording in Music Studio, click **Split stems**, then choose **Isolate piano**. Save or play **Piano.wav** and **Accompaniment.wav**. This extracts piano already present in the recording. The main **Five stems** action saves each standard group independently. Piano isolation uses bundled Spleeter five-stem weights; it runs locally without a model download. See [model provenance and limits](RELEASE-0.12.0.md).

## Five separate tracks

In Music Studio, choose **Split stems → Five stems**. Blaze saves **Vocals.wav**, **Drums.wav**, **Bass.wav**, **Piano.wav** and **Other.wav**. Each can be played or exported independently. **Isolate piano** remains available for a piano-only track plus accompaniment. These are five standard groups; guitars, strings and other remaining instruments are grouped into Other. See [release details](RELEASE-0.13.0.md).

## Nine instrument tracks

Choose **Nine stems** to split the remaining music into Guitar, Strings, Brass, Synths and Other while preserving Vocals, Drums, Bass and Piano. The track list scrolls while export and close controls remain visible. These are estimates and may contain bleed; no instrument-presence detection is promised. See [release details](RELEASE-0.14.0.md) and [model evidence](MAC-INSTRUMENT-RESEARCH.md).
