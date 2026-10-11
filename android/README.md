# Blaze Android APK preview

A native Android interface with embedded Python/yt-dlp. Termux is not required.
Android 7+ on ARM64 phones or x86_64 emulators. This is a separate 0.1.0 preview,
not the desktop application's complete feature set.

Paste an HTTPS link or share one from another app, choose Video or Audio, and tap
Download. Downloads continue in a foreground service. Use Stop to cancel; retry
the same link to resume a partial file when supported by the site.
Completed files appear in Saved files. Save a copy with Android's folder picker
or share them. Files kept only inside Blaze are removed when you uninstall it.

Video uses a stream which already contains sound. Audio keeps its original
format. No FFmpeg conversion, separate-stream merging, playlists, cookies/login,
aria2, JavaScript runtime, or automatic extractor update is included. Websites
which need those features can fail; use the Termux version for the full CLI.

## Build

Use JDK 17, Python 3.12, Android SDK 35, and the checked-in Gradle wrapper:

```sh
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

The installable, debug-signed APK is `app/build/outputs/apk/debug/app-debug.apk`.
This preview is for sideload testing, not a Play Store release. A debug key is
generated locally by Android tooling; do not use it as a production signing key.
For a public release, the owner must retain a private release keystore so future
updates keep the same signing identity. Keystores are never committed.

The Android APK workflow builds a downloadable artifact for each PR and main
push touching this project. It does not publish a release automatically.

## Ownership and dependencies

Blaze UI/backend code uses the repository's free-use license. Embedded Python,
yt-dlp, Chaquopy, and AndroidX retain their own licenses. See the app's About page
and `app/src/main/assets/`. No GPL Android wrapper or FFmpeg binary is bundled.

Compilation and backend checks do not establish physical-device compatibility.
Before promotion: test install, share input, actual video/audio download,
notification, background/rotation, cancel/resume, export, and uninstall behavior
on a physical Android phone.
