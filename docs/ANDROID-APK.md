# Blaze Android

Install the [0.8.0 preview APK](https://github.com/Brooth-C/blaze/releases/download/android-v0.8.0-preview/Blaze-Android-Preview.apk)
on an Android 7+ ARM64 phone. Blaze has downloads,
local playback and Music Studio in one app.

1. To download: paste a media link, choose Video or Audio and its format, and
   tap Add to queue. Completed files are available in Library and History.
2. To find chords: tap Studio in the bottom navigation, choose a
   local audio/video file and tap Analyse chords. Completed downloads can also open in Studio through More.
3. Play along with the smooth timeline and current/next piano or guitar diagrams.
   Tap the timeline to seek. Choose Options for instruments, edits, loop, transposition,
   timing corrections and JSON/CSV exports.

Advanced analysis and beat/downbeat detection run locally with pretrained models.
Nothing needs training and no microphone is used. Blank chord cells indicate
no new recognised chord; uncertainty is retained in exports. Complex mixes may
need manual correction. Transposition changes diagrams/labels, not audio pitch.
Analysis is cancellable; repeated analysis of the same file/model uses the cache.

Downloading needs an internet connection; local analysis does not. Some sites
require login or block automated downloads. Blaze cannot guarantee those sites
will accept a request. WAV/FLAC conversion cannot restore lost source quality.

Save a copy of your media outside Blaze before uninstalling. An in-place upgrade
requires the same signing key. Preview CI builds can use different debug keys, so Android may require uninstalling the older preview first. Export downloads with **Save a copy…** before doing that; uninstalling removes app-private data. See [build and licensing details](../android/README.md).
