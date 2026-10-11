# Android app preview

Blaze now has a native Android app project in [`android/`](../android/README.md).
It includes its own Python/yt-dlp runtime and does not require Termux.

The initial APK is a **debug-signed preview** for Android 7+ ARM64 phones.
It supports HTTPS links, video with sound, original-format audio, foreground
downloads, cancellation, resumable partial files when supported, sharing, and
export to a folder chosen with Android's document picker.

**[Download the Android APK](https://github.com/Brooth-C/blaze/releases/download/android-v0.1.0-preview/Blaze-Android-Preview.apk)** · [Preview release and checksum](https://github.com/Brooth-C/blaze/releases/tag/android-v0.1.0-preview)

Install the preview APK. Allow installation from that source when Android asks, then open
Blaze. Paste a link, choose Video or Audio and tap Download. You can also share
a link from another app to Blaze.

The app keeps files in its own storage; use **Save a copy…** to put completed
downloads in your public Downloads folder. Uninstalling Blaze deletes files
which you have not exported. No broad storage permission is requested.

This preview does not include MP3 conversion, separate-stream video/audio
merging, playlists, login/cookies, or a JavaScript runtime. Some services will
fail. The [Termux version](ANDROID.md) retains the full command-line workflow.

The preview has not been validated on a physical Android phone. Build/lint and
backend tests are not a substitute for testing actual service downloads and
background behavior on your device. This is not a Play Store release.

Debug APKs from different CI runs can have different signing keys. If Android
refuses an update, export your saved files before uninstalling the old preview.

The APK code follows Blaze's free-use license. Bundled third-party licenses are
included under `android/app/src/main/assets` and summarized in the app's About
dialog. Production releases need an owner-controlled private signing key.

## Validation and builds

The Android workflow compiles the APK, runs lint and backend safety tests, and
opens the app and embedded Python runtime in an Android 10 x86_64 emulator.
It captures an actual foreground-app screenshot. Local HTTPS MP4 and Ogg
sample downloads also passed; broad website and physical-device behavior are
not established by those checks.

PR builds remain temporary artifacts. A validated main build publishes a new
version as a separate Android prerelease, with the APK, screenshot and checksum.
The desktop/Termux stable release remains the default Latest release. Existing
Android preview assets are never replaced, preserving their signing identity.
