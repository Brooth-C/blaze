# Blaze Android 0.6 preview

Blaze combines downloads, local playback and Music Studio in one Android app.
Android 7+ ARM64 phones are supported; x86_64 is included for emulator testing.

Music Studio defaults to the same verified BTC-170/MusicXLab advanced ensemble
as Windows, using shared NumPy CQT and sequence decoding and native ONNX Runtime.
Beat This! detects beats/downbeats locally; consistent intervals determine meter.
Manual timing overrides take precedence. No microphone permission, model download,
training, server or audio upload is needed. Advanced extensions and slash chords
are supported, but dense music can still need manual correction. Uncertain
segments remain X in exports and appear blank in the timeline.

Import audio/video from the home screen or open a completed download in Studio.
Playback, the smooth chord timeline and current/next piano or guitar diagrams
share one phone screen. Editing, rhythm overrides and JSON/CSV exports are in
Studio options. Analysis is cancellable and cached by media/model identity.

## Build and validate

Use JDK 17, Python 3.12, SDK 36 and build-tools 35.0.0. The unchanged native
libraries and pretrained models are reused from immutable, checksum-verified
Blaze releases; their build recipes/provenance remain available.

```sh
python tools/stage_android_studio.py --work build/android-released-assets
python tools/sync_android_harmony.py
python -m pip install numpy==1.26.4 onnxruntime==1.20.1
python tests/Blaze-Android-Harmony-Tests.py
python tests/Blaze-Android-Rhythm-Frontend-Tests.py
cd android
./gradlew lintDebug assembleDebug assembleDebugAndroidTest
```

The Android workflow validates backend, decoder and portable-engine behavior,
then exercises the actual app on isolated API 29/35 emulators. Instrumentation
checks import visibility, 48dp controls, portrait/landscape, large text, playback,
cache/cancellation and native chord/rhythm inference, and captures screenshots.
Never run queue/removal tests on a user's production downloads.

## Sources and licenses

Models: BTC-170, five MusicXLab checkpoints and Beat This!, all verified MIT.
Portable CQT adaptations retain librosa's ISC notice. NumPy/OpenBLAS and the
numerical runtime retain their notices, including the GCC Runtime Library
Exception for libgfortran. Blaze's license does not replace third-party rights.

FFmpeg/LAME and LibVLC remain separately replaceable LGPL-only components. All
ten bundled native binaries match v4.1.29 byte-for-byte. Their exact corresponding
sources and build recipes are available at:
https://github.com/Brooth-C/blaze/releases/download/v4.1.29/Blaze-Android-Native-Sources.tar.gz
SHA256: c2eeadf7bbc8be426ead9248fa69e4a5ce5c490c5484669495e684a3081d226e

The APK is debug-signed for testing. Keep the same signing key for an in-place
update. If Android reports incompatible signatures, export your files before
uninstalling the older preview. Public sites may independently block downloads;
local analysis continues to work without an internet connection.
