# Studio refinement verification

Scope: local authenticated Blaze; never script the Apple reference service.
Existing fixture servers create isolated data and real WAVs. Controlled musical
results and separation outputs are explicit; they do not prove model quality.

| Flow | Automated evidence |
| --- | --- |
| F01 import/playback/navigation | Desktop UI, Mac Design UI; real local WAV/video decode, one player, stale import protection |
| F02 analysis/visualisation | Harmony UI; empty state, unequal 25/75% subdivisions in a bar, current/next, detected/unknown meter |
| F03 timeline interaction | Harmony UI; click/keyboard seeking, follow/group, 8-bar scroll, timing-position readout |
| F04 panels | Harmony + Studio UI; keyboard resize/collapse, inspector toggle, narrow/wide viewport fit |
| F05 details/settings | Design + Studio + Desktop UI; chord drawer/notation, settings, keyboard shortcuts, dark/light/reduced motion |
| F06 background stems | Stems UI + Stem Jobs Python; close/reopen/cancel/retry, source isolation, nine/five output modes and WAV export |
| F07 discovery | Desktop Discovery UI; controlled search/debounce/error/retry/empty/stale cancellation, persistent playback |
| F08 packaged Mac | macOS 26 Apple Silicon workflow; actual bundle UI smoke now requires visible proportional chord regions and valid transport |

Fresh local logs and screenshots: /workspace/mac-ui-refinement/. The packaged
Mac job is a separate required result, not inferred from Linux browser tests.
VoiceOver, physical audio latency, sustained model-load profiling and direct
Logic runtime inspection are not available locally. No payment/login/cloud
permission states are introduced. Existing authenticated loopback access remains.
