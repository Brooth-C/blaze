# Blaze Android 0.2 preview

Adds the requested queue, history, quality choices, background handling,
MP3 conversion, high-quality video merging and bounded playlist support.

- Persistent, transactional queue with duplicate protection, interrupted-work recovery and 200-entry admission limits.
- Separate Queue, History and Files views; pagination keeps older records accessible.
- Original audio, MP3 (192 kbps), M4A, WAV and FLAC; maximum video quality choices through 4K where the site offers them.
- Native FFmpeg/LAME conversion and MKV stream merging, built from verified source for ARM64/x86_64.
- QuickJS and bundled ejs for supported extractor JavaScript challenges.
- Stop-item, pause-queue, resume and retry; stale stop requests cannot cancel a newer job.
- Foreground progress and Android timeout handling; queue state remains saved when the app rotates or is interrupted.
- Separate Open/Share actions, foreground document-picker exports, export admission protection and guarded partial/file removal.
- Legacy file import when the same signing key permits an upgrade.

Validation includes backend safety cases, real local HTTPS conversion/merging
and stopped-conversion retry, Android lint and instrumented Android 10/15 tests
with synthetic media. Native licenses and the exact corresponding source/build
archive accompany the release.

This remains a debug-signed preview. Physical-phone and broad public-service
behavior are not established. Live streams, login/cookies and parallel downloads
are not included. WAV/FLAC do not restore lost source detail. Export media before
uninstalling an older preview when signing-key differences prevent updating.
Production releases need an owner-controlled signing key for future upgrades.