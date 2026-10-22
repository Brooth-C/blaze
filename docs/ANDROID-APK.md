# Blaze Android

Install the [0.11.0 Android APK](https://github.com/Brooth-C/blaze/releases/latest/download/Blaze-Android-Preview.apk)
on an Android 7+ ARM64 phone. Explore, downloads, playback and Music Studio live in one app.

1. Open Explore for real YouTube music picks and thumbnails, or search for songs, videos, artists and playlists without copying links. New users get general music discovery; listening, favourites and repeat listening inside Blaze personalize later picks without YouTube login. Use Music/Videos or Refresh to update recommendations. The profile button explains this and can reset listening history.
2. Search updates after a short typing pause; use the keyboard Search action to submit immediately. All includes ordinary YouTube videos, channels and playlists; Songs searches music, and Videos narrows results to video. Results update without replacing the search editor or cursor. Returning to a recent search can reuse its short-lived on-device cache. Tap a recording to play it; Now Playing and the mini-player share the same listening session, with seek, queue and playback controls.
3. Tap Download to choose audio/video and a format. Downloads keeps the durable queue and its History; Library contains completed files. You can also paste a supported HTTPS media link in Downloads.
4. Tap Open in Studio for a saved recording, or save an online recording for Studio first. The Studio tab also imports local audio/video. Use Video for an inline preview or fullscreen without reopening the file; playback position and pause state stay with the same player. Drag the timeline to choose a position, then release to seek. Tap Analyse chords after opening the local file.
5. Play along with the timeline and current/next piano or guitar diagrams. Tap the timeline to seek. Choose Options for instruments, edits, loop, transposition, timing corrections and JSON/CSV exports.

See the native [Explore](https://github.com/Brooth-C/blaze/releases/download/android-v0.11.0/Blaze-Android-Explore.png),
[Search](https://github.com/Brooth-C/blaze/releases/download/android-v0.11.0/Blaze-Android-Search.png) and
[Now Playing](https://github.com/Brooth-C/blaze/releases/download/android-v0.11.0/Blaze-Android-Now-Playing.png) captures.
They use demonstration metadata, thumbnail fixtures and local synthetic audio for reproducible UI checks.

Listening history and repeat counts stay on-device. Blaze sends short artist/song
queries to YouTube, then filters and diversifies the returned candidates; it does
not copy a signed-in YouTube feed. Recommendations exclude recently heard tracks.
Six-hour metadata caches can preserve picks during offline refresh failures.

Advanced analysis and beat/downbeat detection run locally with pretrained models.
Nothing needs training and no microphone is used. Blank chord cells indicate
no new recognised chord; uncertainty is retained in exports. Complex mixes may
need manual correction. Transposition changes diagrams/labels, not audio pitch.
Analysis is cancellable; repeated analysis of the same file/model uses the cache.

Online search, streaming and downloads need an internet connection and depend on
upstream provider availability and the pinned yt-dlp extractor. Some sites require
login or block automated requests. Local playback and analysis work offline.
WAV/FLAC conversion cannot restore lost source quality.

Save a copy of your media outside Blaze before uninstalling. An in-place upgrade
requires the same signing key. Debug-signed CI builds can use different signing keys, so Android may require uninstalling the older build first. Export downloads with **Save a copy…** before doing that; uninstalling removes app-private data. See [build and licensing details](../android/README.md).
