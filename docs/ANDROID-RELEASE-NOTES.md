# Blaze Android 0.1.0 preview

Standalone Android APK with Blaze branding and touch controls. Requires Android
7+ on ARM64 phones; x86_64 is included for emulators. Termux is not required.

- Paste or share an HTTPS link and choose video or original-format audio.
- Download one item in a foreground service, view progress and stop it.
- Retry supported partial downloads, share completed files, or save a copy with Android's folder picker.
- Embedded Python/yt-dlp runtime and third-party license notices.

This is a **debug-signed preview**, not a Play Store or production-signed release.
Audio conversion, separate video/audio merging, playlists, cookies/login,
JavaScript runtimes and automatic extractor updates are not included. Some
websites will fail. Export your files before uninstalling the app.

Backend safety tests, Android lint, compilation, emulator UI/runtime startup,
foreground-app screenshot and local HTTPS video/audio samples passed.
Physical-phone downloads, background behavior, storage and broad service
compatibility still require validation. Future production updates need an
owner-controlled signing key. Different debug builds may not install over each
other; exported files survive removing the old preview.

The APK, SHA256SUMS-Android.txt and emulator screenshot are attached to this
prerelease. Existing version assets are not replaced.
