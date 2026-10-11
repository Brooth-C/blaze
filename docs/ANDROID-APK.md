# Android app preview

Blaze now has a native Android app project in [`android/`](../android/README.md).
It includes its own Python/yt-dlp runtime and does not require Termux.

The initial APK is a **debug-signed preview** for Android 7+ ARM64 phones.
It supports HTTPS links, video with sound, original-format audio, foreground
downloads, cancellation, resumable partial files when supported, sharing, and
export to a folder chosen with Android's document picker.

Install the preview APK from the APK build artifact or the file supplied by the
maintainer. Allow installation from that source when Android asks, then open
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

The APK code follows Blaze's free-use license. Bundled third-party licenses are
included under `android/app/src/main/assets` and summarized in the app's About
dialog. Production releases need an owner-controlled private signing key.
