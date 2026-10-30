# Studio refinement verification

Base: main 03cc2cf (Mac 0.16.0). Candidate: Mac 0.17.0, Apple Silicon / macOS 26.
Other platform application releases and old installer checks remain unchanged.

## Fresh local results

- Six browser suites pass: Mac Harmony, Studio, Design, Stems, Desktop and Desktop
  Discovery. Real WAV/video decode and loopback routes; controlled recognition,
  recommendations and separation fixtures. No live provider or model-quality claim.
- Python: Runtime 22, Presentation 4, Chrome 21 (one platform-specific skip),
  Waveform 12, Stem Jobs 14, immutable publisher 7: pass.
- Node: Live Flow, Timeline Cells and Automatic Rhythm: pass.
- Ruff F/E9 on changed Python, JS syntax and git diff whitespace: pass.
- Replica contrast checker: all 13 specified pairs AA; lowest normal-text pair
  4.69:1. This does not cover every legacy surface or certify full accessibility.
- Frontend direction local evidence-record checker: complete. It checks record
  completeness, not visual truth; rendered screenshots were separately reviewed.
- Five-second Chromium local-WAV playback sample: 300 intervals, median 16.7ms,
  p95 16.7ms, zero long tasks, real media time advanced. Not physical-device FPS,
  sustained CPU/GPU, model-load or native audio-latency proof.

External artifacts: /workspace/mac-ui-refinement, including final-*.log,
contrast.json, design-evidence.json, after/performance.json and taste-audit/.

## Visual evidence

- Before: before/mac-studio-workspace-wide-dark.png.
- After: after/mac-studio-workspace-wide-dark.png (same fixture/state/viewport).
- Comparison: before-after.png.
- Official reference: /workspace/mac-studio-next/logic-research/official-main.png.
- Matching window-size capture: after/blaze-matched-light.png (1304×824).
- Reference side-by-side: reference-side-by-side.png; different session content
  is explicit. Apple images are not copied into the repository or app bundle.
- Details: after/chord-tools-light.png; real voicing diagrams inherit graphite.
- Harmony: after/mac-harmony-subdivisions.png and four light/dark viewport pairs.

Replica's matched-width control-bar layout comparison returned **57.9, partly**,
with about -3.2% normalized height difference. Its edge-density map flags the
missing unsupported recording/count-in buttons, extra Blaze time/LCD fields and
different control grouping. This is not a whole-app quality or fidelity score.
The earlier unmatched-width experiment is retained as iteration history, not
used as final evidence. No claim of pixel equivalence is made.

## Review rubric

This is a subjective self-review of the rendered browser workspace, not an
independent evaluation or native fidelity certification.

| Category | Weight | Awarded | Evidence / remaining difference |
| --- | ---: | ---: | --- |
| Workspace architecture | 25 | 21 | Integrated transport, inspector, tracks and editor; primary chord strip deliberately adds a Blaze-specific region |
| Toolbar/type/control fidelity | 20 | 15 | Compact LCD/system typography, aligned real controls; grouping differs and no unsupported record controls |
| Chord/musical presentation | 20 | 18 | Real 25/75% segmentation, follow, measured beats, unknown-meter honesty, current/next; no full song arrangement editing |
| Surfaces/icons/polish | 15 | 12 | Coherent graphite and flat drawer, Blaze icons; not Logic's proprietary artwork and control renderer |
| Integrity/interaction/accessibility | 20 | 15 | Six rendered suites, contrast/focus/keyboard/resize; native VoiceOver and physical performance remain separate |
| Total | 100 | 81 | Recognizably DAW-inspired; no full Logic parity claim |

## Remaining verification and limits

The macOS 26 workflow must verify the actual packaged AppKit/WebKit application,
including new visible chord-region/four-bar/transport assertions. Linux browser
results cannot replace that check. Native VoiceOver, physical device audio
latency, sustained loaded-model performance and direct Logic runtime inspection
are unavailable here. The existing package is ad-hoc signed, not notarized.

Taste's actual probes retain small-text/no-visible-h1/font-count findings for
legacy/hidden app content and deliberate compact LCD metadata. These are not
reported as clean. New controls have names, boundary announcements and keyboard
alternatives; the project title is retained with a screen-reader h1.

Skill-by-skill execution and skips: [MAC-UI-SKILLS.md](MAC-UI-SKILLS.md).
Reference sources/confidence: [reference-spec.md](../replica/reference-spec.md).
