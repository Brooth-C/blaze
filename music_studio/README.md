# Blaze desktop

Explore, Downloads, Library and Music Studio share one desktop app on Windows,
Mac and Linux. Desktop 0.9.0 refines the Mac workspace with native navigation and
a compact listening layout. Windows and Linux retain the discovery and playback
workflow introduced in 0.8.0. Mac 0.10.0 adds a simple, local four-stem separation workflow on Apple Silicon. New Mac builds target Apple Silicon only; the final Intel 0.9.0 build stays available. Terminal installers keep their separate version and behavior.

## Stem separation on Apple Silicon

Open a recording in Studio and choose **Split stems** to create vocals, drums,
bass and other instruments with one bundled SCNet model. Processing is local,
with progress and cancellation. Finished stems can be played and exported as
WAV files. Piano and guitar are not separate outputs, and some leakage or
artifacts can remain. The model and its notices are separate from the unchanged
chord-recognition bundle.

## Discover and listen

Open Explore for general music recommendations, or search for songs and videos
without copying a link from another app. Recommendations use listening inside
Blaze without a YouTube login. History stays on this device; recommendation
requests send search terms to the provider. Choose Reset listening history in
Explore to start over.

Choose a result to prepare a local playback copy, then listen through the same
player while navigating the app. Preparation needs internet and can be cancelled.
Use Download to choose a format and save a permanent copy in the regular download
folder, or Open in Studio to analyse the current copy. Provider restrictions, network speed and the
available source determine whether preparation succeeds. The playback cache is
bounded and is separate from Library's saved downloads.

Playback preparation selects AAC audio or AVC/AAC video up to 720p for renderer
compatibility; Downloads retains the wider quality choices. Preparation is
limited to 512 MiB and two minutes per item. The cache keeps up to six copies
within 1 GiB while preserving the selected media.

Library still searches and filters completed downloads. Import file in Studio
opens audio or video already on your device; no network is needed for analysis.

Import local audio/video and analyse it offline. The default advanced recognizer
combines the original MIT BTC-170 model with Music X Lab's verified five-model
structured ensemble. It supports richer chord candidates and inversions, including
ninths, elevenths and thirteenths. Predictions are not guaranteed correct; a broader
vocabulary is not an accuracy benchmark. Uncertain passages display blank, while
the original uncertainty remains in exported analysis data.

Musical sequence decoding discourages transient flips without forcing every change
onto a beat. Equivalent pitch-class evidence is combined rather than discarded;
strong bass evidence can help name equivalent chords. Beat This! detects beats and
downbeats locally. Consistent runs determine bar grouping; weak runs remain ungrouped.
Pulse counts do not always identify a notation denominator. Manual timing overrides
and chord corrections remain available through Settings.

On Mac, a native source-list sidebar and toolbar frame the WebKit workspace.
Search, local import and Settings are available from that toolbar. The compact
player stays with the workspace while you browse; choosing a recording keeps
Explore open, and the expanded player opens on request. Studio keeps its timeline
and notation in the main area, with song details available separately. Native
chrome uses system glass on macOS 26 and a system-material fallback on older Macs.
The content and playback engine remain shared web components.

In compact Windows and Linux Studio windows, video and song details open in a
dialog. Transpose changes chord labels and diagrams, not the recording's pitch.
Piano/guitar diagrams show suggested voicings.

## Rebuilding

For the Windows package, use Python 3.12 on Windows x64 in a private environment.
See the [Mac](../docs/MACOS.md) and [Linux](../docs/LINUX-DESKTOP.md) guides for
their native packaging requirements. Windows runtime dependencies:

```
numpy==1.26.4
onnxruntime==1.20.1
pywebview==6.1
rich
mutagen
```

Build-only dependencies include PyInstaller 6.16.0, Pillow 11.3.0, CPU PyTorch 2.6.0,
torchaudio 2.6.0+cpu, onnx 1.17.0, librosa 0.10.2.post1, soxr 1.1.0, einops 0.8.1,
rotary-embedding-torch 0.8.6 and the BTC frontend's documented legacy librosa 0.6.3.
Torch, librosa, SciPy and the compiler are not shipped in the application runtime.

Exporters run in this order, using pinned upstream source revisions and published
checkpoint checksums (see each model manifest):

1. `tools/build_music_models.py`: original BTC weights and its portable frontend.
2. `tools/build_lv_frontend.py --output music_studio/models/lv_cqt.npz --verify`.
3. `tools/build_structured_models.py --source PATH_TO_LV_CHORDIA --output music_studio/models`.
4. `tools/build_rhythm_model.py --source PATH_TO_BEAT_THIS --checkpoint PATH_TO_FINAL0 --output music_studio/models`.
5. `tools/build_windows_studio.py --ffmpeg PATH_TO_LGPL_FFMPEG --ytdlp PATH_TO_YTDLP --node PATH_TO_NODE --output DIST --work BUILD`.

The GUI builder stages a private downloader copy with hidden child-process windows;
it does not modify terminal installer source. Only verified release model assets are
staged. No ChordFormer or ChordMini-refined weights are bundled in this release.

## Licenses and validation

BTC, Music X Lab and Beat This! notices accompany their model files. The portable
LV frontend retains librosa's ISC notice. The external Windows FFmpeg executable is
an LGPL-only build; matching FFmpeg, LAME, Ogg, Vorbis and Opus sources, configuration,
build recipe and notices are included in the downloadable ZIP. It is replaceable
independently of Blaze. Third-party files retain their own licenses.

Run the focused Python evidence/meter/sequence and desktop discovery tests, plus
JavaScript timing and Playwright workflow tests in `tests/`. Discovery UI tests
use controlled provider metadata and real local media. Native package workflows
exercise their actual renderer separately. These checks do not establish live
provider availability, annotated real-song chord accuracy or physical-device
frame rates.
