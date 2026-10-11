# Blaze Android 0.5 preview

A native touch interface with embedded Python/yt-dlp, verified native FFmpeg/LAME,
and QuickJS. Android 7+ on ARM64 phones or x86_64 emulators; no Termux required.

The app supports persistent queue/history, quality selection, MP3/M4A/WAV/FLAC
and original audio, video/audio merging, bounded playlists, pause/resume/retry,
notifications, player opening, sharing, foreground export and guarded removal.
See [the user guide](../docs/ANDROID-APK.md).

The offline chord finder accepts completed downloads and locally selected audio
or video. Bundled FFmpeg streams mono audio to an original Java harmonic-analysis
engine, without a server, model download, or microphone permission. Results are
saved by media content, with timed playback, label transposition, and locally
drawn piano/guitar triad diagrams. This is a major/minor baseline, not an evaluated
neural recognizer; dense recordings can be inaccurate. See the guide for limits.

## Build and test

Use a disposable Linux runner with JDK 17, Python 3.12, SDK 36 and NDK 28.2.
Run `bash android/native/build.sh arm64-v8a` and `x86_64`, then copy each
`build/android-native-ABI/package/` into `android/app/src/main/` (merge folders).
Native binaries and generated license assets are ignored by Git.

```sh
python -m pip install yt-dlp==2026.8.19 cryptography imageio-ffmpeg
python tests/Blaze-Mobile-Tests.py
python tests/Blaze-Mobile-Integration-Tests.py
python tests/Blaze-Mobile-Chord-Tests.py
cd android
./gradlew lintDebug assembleDebug assembleDebugAndroidTest
```

The workflow performs those steps, checks native programs from source, and runs
instrumentation on fresh Android 10/API29 and Android 15/API35 x86_64 emulators.
Tests cover actual MP3 conversion/merge/probe/JavaScript execution, queue
persistence/claims/overflow/pagination/removal, pause/resume, and rotation.
Synthetic media is generated for the tests; never run lifecycle tests over an
existing user's production queue or downloads.

The APK is debug-signed for preview testing. Source/native notices and exact
corresponding source archives accompany versioned prereleases; old version
assets are never overwritten. For production upgrades, the owner must retain a
private signing key. Do not commit signing keys. Different preview keys can
require exporting files before uninstalling the old app.

## Ownership

Blaze UI/backend use the repository's free-use license. The LGPL FFmpeg/LAME
programs, MIT QuickJS/Chaquopy, Unlicense-covered yt-dlp/ejs, Python and AndroidX retain
their own licenses and replacement/rebuilding rights. See [native build details](native/README.md)
and APK assets. No GPL media features are enabled.

Passing emulator tests is evidence for those cases, not a guarantee about all
phones or changing public services. Live streams, login/cookies and parallel
media downloading are not implemented in this version.
