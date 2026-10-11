# Blaze Android 0.3 preview

Adds an audio/video player inside the Blaze APK, powered by AndroidX Media3/ExoPlayer.

- Tap Play on a completed download in Files or History.
- Play/pause, seek, ten-second skips, playback speed and single-file repeat.
- Fullscreen video and embedded subtitle controls where tracks are available.
- Position, speed and pause state survive rotation; saved positions are remembered when reopening a file.
- Playback releases its decoder and audio focus when you leave the player screen; headphone disconnection pauses playback.
- Missing, unfinished or out-of-folder files are rejected. Codec failures show a useful error inside the player.
- Queue/history, quality choices, conversion, stream merging and playlists remain available.

The player is part of Blaze; no separate player app is required. Playback codec
support depends on the Android device. This version does not include background
music playback or picture-in-picture. Physical-phone validation remains outstanding.

This is a debug-signed preview. Export files before uninstalling an older build
if signing-key differences prevent updating. An owner-controlled production key
is needed for reliable future upgrades.

Media3 and its supporting libraries keep their Apache 2.0 licenses. Native
FFmpeg/LAME/QuickJS licenses and corresponding sources accompany the release.

[Setup and player guide](https://github.com/Brooth-C/blaze/blob/main/docs/ANDROID-APK.md) · [Previous Android release](https://github.com/Brooth-C/blaze/releases/tag/android-v0.2.0-preview)
