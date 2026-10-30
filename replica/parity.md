# Verification status

Local regression checks cover the implemented Studio/workflow slice, not parity
with the complete Logic Pro application. Reference screenshots are different
sessions and are not used to invent a numerical pixel-fidelity score.

The rendered checks exercise real WAV files and authenticated waveform/export
routes with a controlled separator. They verify always-visible workflow actions,
selection identity, keyboard behavior, compact geometry, seeking/zoom, shared
playback, nonmodal progress, cancellation and completed output export. Backend
checks run chord and separation workers concurrently and verify that importing
another recording cannot replace the separation input. These are functional
checks; they do not measure learned-model quality or physical-device smoothness.

Taste's actual browser probes were run at1440,1024 and780px. Reports and
screenshots stay in the external work evidence directory. Generic h1/tiny-text
warnings remain documented in design/components.md rather than suppressed or
reported as passes. Replica's before/after pixel diff records the intentional
workflow/layout changes; it is not a claim of full Logic visual equivalence.

Release readiness still requires real macOS26 packaged-app/background-task
checks and live YouTube video/song search. The current local network denied a
YouTube proxy connection; fixture search is not substituted for live proof.
The workflow gates packaging on live source-engine search and repeats search
with the actual packaged downloader before publishing.
