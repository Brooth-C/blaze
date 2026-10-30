# Blaze for Mac 0.16.0

Stem separation runs as an independent background job. Its recording is copied
on the worker so opening another file does not change or remove the recording
being separated. Browse, playback and chord analysis remain available. A
persistent task button shows separation progress and reopens its controls.
Cancelling chord analysis and cancelling stem separation are separate actions.

Search uses yt-dlp's bounded search extractor for ordinary video searches. The
Mac downloader is pinned to yt-dlp 2026.10.26 with EJS 0.8.0.

Studio keeps Browse, Split Stems, Analyse Chords, Chord Tools and the selected
stem's Save WAV action in a visible action bar. Track lanes show actual audio
waveforms; the lower Chord Guide is explicitly derived from recognition.
Unavailable recording/editing controls are omitted. An undetected key stays
blank. Only the selected audition is metered. Playheads use cached geometry and
transforms, and separation uses macOS utility-priority work with a scoped
activity to keep processing while Blaze is open in the background.

This release targets Apple Silicon and is validated on macOS 26.
