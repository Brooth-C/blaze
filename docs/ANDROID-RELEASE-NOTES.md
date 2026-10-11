# Blaze Android 0.5 preview

Find chords offline in local audio/video and completed Blaze downloads.

- Local FFmpeg audio extraction and streaming Java harmonic analysis; no upload, server, microphone, or model download.
- Current/next chords follow embedded playback, with a seekable timeline and estimated song key.
- Save results by media content and reuse them offline; changed media is analysed again.
- Transpose chord labels and locally drawn guitar/piano diagrams without changing playback pitch.
- Cancel analysis; leaving the screen releases processing and removes temporary document copies.
- Major/minor triads only. Ambiguous passages are marked N; complex chords and beat/BPM detection are not implemented.

This is an initial harmonic baseline. Synthetic tests do not establish accuracy
on full music mixes or equivalence to Chord AI. Listen and correct uncertain
passages by ear. See the [chord finder guide](https://github.com/Brooth-C/blaze/blob/main/docs/ANDROID-APK.md).

## Previous: 0.4 preview

Play original downloads inside Blaze with embedded LibVLC and broader codec support.

- Automatic hardware decoding and a Software option for unsupported hardware codecs.
- Original MKV playback, audio/subtitle track selection, seeking, speed, repeat and fullscreen controls.
- Files → Open an audio or video file plays an existing file directly through Android's picker.
- An optional Android playback engine remains available inside the same app.
- Playback pauses outside the foreground and on headphone disconnection or audio focus loss.
- Black logo background in system dark mode and white in light mode, including adaptive launcher resources.
- LGPL-only native LibVLC built from pinned sources; matching decoder sources and build instructions accompany the APK.

Codec support does not guarantee smooth 8K/16K playback on low-end phones.
Damaged or encrypted files may not play. No redownload or transcoding is required
to use the player. Physical Redmi validation remains outstanding.

This is a debug-signed preview. Export files before uninstalling an older build
if signing-key differences prevent updating. An owner-controlled production key
is needed for reliable future upgrades.

[Player guide](https://github.com/Brooth-C/blaze/blob/main/docs/ANDROID-APK.md) · [Previous Android release](https://github.com/Brooth-C/blaze/releases/tag/android-v0.3.0-preview)
