# Blaze Android app â€” 0.5 preview

[Back to Blaze](../README.md)

**[Download the APK](https://github.com/Brooth-C/blaze/releases/download/android-v0.5.0-preview/Blaze-Android-Preview.apk)** Â· [Release, screenshots, checksums and native sources](https://github.com/Brooth-C/blaze/releases/tag/android-v0.5.0-preview)

Requires Android 7+ on ARM64 phones; x86_64 is included for emulators. Python,
yt-dlp, FFmpeg/LAME and QuickJS are bundled. Termux is not required.

## Download, convert and queue

1. Paste an HTTPS link, or share one from another app to Blaze.
2. Choose Video and maximum quality, or Audio and Original/MP3/M4A/WAV/FLAC.
3. Enable playlist mode for a playlist of up to 200 entries. Oversized lists are rejected rather than silently truncated.
4. Tap Add to queue. Work is processed sequentially; adding items to a paused queue keeps it paused.

Quality is a maximum where the site offers resolutions. Direct media links are
saved as provided. Separate video/audio streams merge into MKV. Audio conversion
uses bundled native tools; WAV/FLAC cannot restore detail missing from the source.

Stop item stops that item and keeps supported partial files for Retry. Pause
queue pauses active work and retains waiting items. Resume queue continues
paused/interrupted work. Failed and explicitly stopped items have Retry buttons.
Queues and history stay saved after rotation or process interruption. Android
and phone power managers may stop or time-limit background services; reopen
Blaze and resume if this happens. Enable notifications for visible progress.

## Files and history

Use Queue, History and Files to filter items. Older records stay accessible with
Previous/Next pagination. Files appear only after a verified completion.
Play opens the completed download inside Blaze's own audio/video player;
Share grants read access to the chosen file.
**Files â†’ Open an audio or video file** opens an existing local file using
Android's file picker. Blaze reads the selected file directly without copying,
converting or downloading it again. The provider must allow read access.
Save a copy uses Android's document picker and a foreground copy service.

## Inbuilt player

Tap **Play** in Files or History. Embedded LibVLC plays the original file inside
the same APK; a separate VLC app, conversion or another download is not required.
The controls include play/pause,
seeking, ten-second skips, playback speed, repeat, embedded subtitles when
available, and fullscreen video. Position, speed and pause state survive rotation.
Blaze remembers your position when you leave the player.

Playback pauses when the player screen leaves the foreground and releases its
decoder/audio focus. Reopen the file to continue. Headphone disconnection pauses
playback. Automatic decoding uses hardware where available. If a file fails,
choose **Decoder: automatic / software**, then **Software** to use bundled codecs.
Software decoding can be slower and use more battery. **Use Android playback
engine** switches to the secondary Media3 player inside Blaze.
Damaged, encrypted or especially demanding files can still fail. Native 8K/16K
playback on every low-end phone is not possible; resolution, codec, frame rate
and bitrate must fit the device's processing capacity.
The player opens completed Blaze downloads or a file you explicitly choose in
Android's picker. It does not accept arbitrary network links or unfinished jobs.

## Offline chord finder (0.5)

Choose **Find chords in audio or videoâ€¦** on the main screen, or **Find chords
offline** beside a completed download. The selected audio/video plays inside
Blaze while the app analyses its first audio track locally. Video frames are
not analysed: the soundtrack supplies the chords. Online sources must first
be downloaded with Blaze; local analysis never uploads media or contacts a server.
No microphone access, account, API key, or model download is needed.

The result shows current/next chords, a timestamped timeline, an estimated key,
and piano/guitar diagrams. Tap a timeline segment to seek there. Transpose
changes labels and diagrams only; the original playback pitch is preserved.
Guitar shapes assume standard Eâ€“Aâ€“Dâ€“Gâ€“Bâ€“e tuning. The estimated key is for the
original recording. Analyses stay saved in Blaze and are reused when the same
media content is selected again. Changing the file triggers a new analysis.

This first engine estimates the 24 major/minor triads. **N** means silence or no
reliable chord. It does not identify sevenths, slash chords, complex voicings,
or tempo/beat grids. Key and chord labels are estimates; dense mixes, vocals,
distortion, unusual tuning, and fast changes can be wrong. Synthetic regression
checks do not establish accuracy on commercial songs. Compare tricky passages
by ear. Chord timing has roughly 0.2-second steps with a 0.74-second analysis window.

Analysis accepts files up to 2 GB and audio up to two hours, streams decoded
samples with bounded memory, and can be cancelled. Keep this screen open:
leaving it cancels unfinished work; reopen and tap Analyse to retry. Rotation
keeps active work. The file picker may reference a cloud provider; choose an
already available local file for airplane-mode use. Selected documents are
copied temporarily into the app cache for decoding, then the copy is deleted.
Results remain in private app storage and are removed on uninstall.
Supported input codecs follow the bundled FFmpeg build; a file can play in
LibVLC yet have an audio codec the chord decoder cannot read. Files without
an audio track and damaged/encrypted files return an error.

The Blaze logo has a white background in the system's light mode and black in
dark mode. Switching system themes refreshes the in-app logo. The launcher icon
uses the same day/night resources; launcher caching can delay its refresh.

Files kept only in Blaze are removed on uninstall. Export anything you want to
keep first. Removing a queued item discards its private partial files after a
confirmation; deleting a completed app file keeps any exported copies.
Existing 0.1 files can be imported when an update uses the same signing key.

## Preview and update limitations

This is a debug-signed preview, not a Play Store release. Different preview keys
can prevent an in-place update. Export your files before uninstalling an old
build; an owner-controlled production key is required for reliable future
release upgrades. APK version and CLI/Termux versions are independent.

Live streams, login/cookies, parallel downloads and automatic extractor updates
are not included. Some sites require access the app cannot provide or block
downloading. Physical-phone and broad public-service compatibility still need
validation; test builds do not imply zero bugs.

## Validation and licensing

The workflow builds verified native tools for ARM64/x86_64, checks backend safety
and real HTTPS conversion/merging fixtures, runs Android lint, and exercises
queue persistence, rotation, pause/resume, concurrent claims, native processing
and runtime startup in Android 10/15 emulators. Tests use synthetic media and
isolated local HTTPS fixtures rather than personal downloads.

Licenses are included in APK assets. LGPL FFmpeg/LAME and MIT QuickJS retain
all their own rights; their corresponding source archives and exact build script
accompany each Android release. Blaze's UI/backend retain the free-use license.
See [native build details](../android/native/README.md).
