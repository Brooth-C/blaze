# Blaze for Windows

Music Studio, Downloads and Library stay inside Blaze. The Windows GUI release is
`windows-v0.6.0`; terminal installers keep their separate version and behavior.

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

The main player fits its window without vertical page scrolling. In compact windows,
video and song details open in a dialog. Transpose changes chord labels and diagrams,
not the recording's pitch. Piano/guitar diagrams show suggested voicings.

## Rebuilding

Use Python 3.12 on Windows x64 in a private environment. Runtime dependencies:

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

Run the focused Python evidence/meter/sequence tests and JavaScript timing tests in
`tests/`. Local checks covered ONNX and frontend parity, synthetic chord comparisons,
the selected real recording, silence, timing, cancellation, edits/exports, six audio
formats, 4K remux/decode and packaged executable operation. Annotated real-song chord
accuracy and physical-device Android behavior are not established by these checks.
