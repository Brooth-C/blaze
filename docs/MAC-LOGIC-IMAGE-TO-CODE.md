# Studio: actual Logic images to working UI

This pass uses the explicitly requested installed image-to-code skill:
`/workspace/shared/agent-skills/image-to-code/SKILL.md`.
Its image analysis, extraction, faithful translation and anti-drift instructions
are applied. The user's named Logic references override the skill's marketing
website, image-generation, hero, spacious-layout and random-variation defaults.
No generated design is substituted for Apple's actual application screenshots.

## Image analysis and implementation mapping

Apple sources were retrieved in the preceding reference study and opened again
before this implementation. Asset URLs and SHA-256 values are retained outside
application assets at `/workspace/mac-studio-polish/logic-research/image-sources.json`.

| Actual image | Visible pattern | Implemented component |
| --- | --- | --- |
| Logic Chord Track / Analyze Chords, Apple Logic overview | Thin purple harmonic lane below ruler, same horizontal project coordinate system as audio | `daw-project-chords`, 32px working lane, timed regions derived from the existing flow map |
| Logic main window, Apple user guide | Flat contiguous header column; names above M/S and level/pan controls | Existing real track headers restacked without introducing Record or Input Monitoring |
| Audio Track Editor, Apple user guide | Lower editor has its own ruler and zoom, stable amplitude gutter, region caption and actual waveform | Existing real editor retained; fixed layout slots preserve it when focus is hidden |

Sources:
- https://www.apple.com/logic-pro/
- https://support.apple.com/guide/logicpro/main-window-interface-lgcpe9cc403a/mac
- https://support.apple.com/guide/logicpro/audio-track-editor-interface-lgcpe9cc446b/mac
- https://support.apple.com/guide/logicpro/global-tracks-overview-lgcp4994bead/mac
- https://support.apple.com/guide/logicpro/track-header-overview-lgcpe53c68af/mac

The 32px lane is a chosen implementation dimension matching the compact visual
relationship, not a claim about Logic's native point measurements. Native scale
of the published figures is unknown. Fonts, icons and track assets remain Blaze's.

## Functional design

The project chord lane and source waveform both use the same full project
duration. Relative positions are start/duration; widths are length/duration.
They align with the same arrangement column and scroll container. Chord click
seeks the actual persistent media player; double-click opens the four-bar focus;
context click uses existing correction. Current state is exposed with
aria-current. Playback drives a transform-only cursor; group DOM is cached.

The former large four-bar strip remains as a separate opt-in focus view through
the Chords disclosure. Its scale is not confused with the full-project timeline.
The 2/4/8-bar controls, follow, resizing and keyboard behavior remain. Background
separation, analysis, exports and the audio/recognition engines are unchanged.

## Render and verify

External evidence: `/workspace/mac-studio-polish/after`.
`mac-studio-workspace-wide-dark.png` is the actual rendered UI using controlled
musical results and real local WAVs; not a design render painted over the app.
Baseline images are under `before`. Reference screenshots are not bundled.

Browser checks verify project/audio column alignment, exact 0.5/64 duration
fraction, project seeking, focus disclosure, four-bar navigation, all viewports,
track selection/mute/pan/keyboard, media playback, drawer and stem actions.
An initial grid-slot regression was reproduced and fixed with explicit slots.
A folder-action test race now waits for its existing route response before
asserting the action occurred; product behavior was not changed to pass it.

This is a local UI preview on `codex/mac-studio-polish`, not a new published Mac
release. Actual macOS 26 package validation and a new immutable release version
are required before publishing this layout. Linux browser evidence does not
establish native WebKit/VoiceOver or physical-device performance.
