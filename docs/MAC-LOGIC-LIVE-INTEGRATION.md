# Approved Studio appearance connected to the local engine

The approved arrangement and lower Audio Editor now open as the default Mac
Studio renderer. The separate `/mac-logic-preview.html` remains a clearly
illustrative, engine-free visual study.

## Connection boundary

`server.py` embeds the main element from the approved preview in an inert
template on Mac responses only. After existing Mac session scripts initialize,
`mac-logic-live.js` mounts that layout and connects it to the small
`BlazeMacStudio.viewState` / `commands` boundary. The shared layout script takes
the live branch before creating any sample tracks or generated waveforms.

The live adapter creates no media player, downloads, jobs, tokens or model
sessions. It obtains real peak data, durations, source revisions, selection,
timing, meters and transport state from the existing engine. Authenticated
stem-selection and original WAV-download routes retain their original owners.
Source generation checks and pending-selection guards remain in the engine.

The former workspace DOM is retained as a hidden, inert internal command
adapter during this incremental migration. Its canvas renderer is suspended;
its session loading, handlers and player remain authoritative. Removing this
internal DOM dependency is a follow-up refactor, not a reason to duplicate
playback or reimplement source ownership in this visual pass.

## Connected behavior

- Real local recording and completed stem rows with their own decoded peaks.
  Empty projects display an import action, not a demonstration song.
- Selection uses the existing stem handoff and retains the current playhead.
- Play/pause, stop, skip, seeking, repeat, volume, track mute, audition and pan.
- Lower stereo waveform, keyboard seeking, time-range selection and zoom with
  a fixed amplitude gutter. This is a waveform viewer/range selector, not a
  destructive audio editor.
- Real chord regions share the complete recording's time scale. Analysis,
  cancellation, project timing and the existing practice drawer are reachable.
- Original stem WAV export; no browser re-encoding.
- Existing separation sheet and background task controls, with focus restored
  to the visible Studio control when the sheet closes.
- Session track list and inspector disclosures. Unsupported recording,
  sequencing and plug-in controls remain visibly disabled.

The existing engine auditions one source at a time. The S control does not add
simultaneous multi-track mixing. Stem count is whatever the actual completed
job produced; no fixed nine-row session is injected.

## Appearance and integration isolation

The approved CSS is scoped to `#logic-preview`, preserving Explore, Downloads,
Library and dialog styles. Mac fallback sidebar/header selectors are narrowed
to the app's direct header so they cannot hide Studio's own transport/editor
headings. Chrome follows the configured macOS-following appearance, with the
existing explicit light/dark settings respected.

Native smoke probes target the new visible renderer. Existing checks and
architectures are retained. No Intel GUI, Android, Windows or Linux renderer is
changed. The shared browser-check workflow adds the production live suite.

## Validation boundaries

Browser plugin not available; installed Playwright/Chromium is used with the
actual authenticated numeric-loopback server. The production live suite uses
distinct real stereo WAV files and controlled separation, so it can verify
selection, waveform identity, playback, exact exported bytes, chord timing,
background operation and rendered geometry without claiming inference quality.
The live suite also applies the real native bridge capability flags in Chromium;
this catches header/navigation CSS regressions but is not AppKit execution.

The older four Mac browser suites explicitly isolate the retained
engine/renderer by stubbing only the two new renderer scripts. This preserves
their internal regression coverage; their results are not presented as proof
of the new default screen. `Blaze-Mac-Logic-Live-Tests.cjs` exercises the
unmodified production page and supplies that proof. The standalone appearance
suite continues to assert zero engine/API calls.

Native AppKit/WKWebView, signing, packaging and macOS 26 validation require the
Mac runner. This Linux session is not evidence that a new Mac binary was built
or released. No release version is changed or published by this integration.

## Second visual comparison

The follow-up used the current listing's Session Players, Stem Splitter and
library images and Apple's Audio Track Editor guide. Normalized measurements,
surface samples and uncertainties are in
`replica/design/logic-current-measurements.json`.

Two inherited CSS rules materially changed the native navigation path: a
generic header reset erased the control-bar fill, and a narrow-screen header
height overflowed its grid row. The live stylesheet now supplies its own fill,
foreground and intrinsic header sizing. Regression checks cover background
appearance, sibling-panel overlap, LCD captions, centered tools and stereo
arrangement rendering under the actual native bridge capability flags.
The generic selected-button background also overrode the chosen audio region's
track color; the clip surface is now explicitly retained through selection and
hover. Compact contextual controls keep clear of the centered tool selector.

The compact musical LCD has separate numeric/caption cells. Context controls,
ruler and chord strip follow the measured screenshot geometry. Track colors
use cool blue/violet roles; real stereo peaks share a common bounded display
gain. Fine musical grid lines derive from actual duration and project timing.
The transport uses the reference's stop/play/record/cycle grouping, with skip
actions retained in Edit. Unsupported capture/record controls stay disabled.

Playwright live and standalone visual suites pass. Substituting the prior live
stylesheet into the new geometry check reproduces the transparent-header
failure; the corrected source passes. Visual evidence is outside the app at
`/workspace/logic-ui-fidelity/`, including original/source crops, before/after
screens and `transport-comparison.png`. The coarse Replica edge-map score for
the narrow control strip improves from 20.1 to 69.6, still classified as partial;
it is not a whole-application fidelity percentage or a native comparison.

## Rotary controls and level faders

The current listing was rechecked as Logic Pro 12.4. Source close-ups expose a
20px pan control with a dark open arc and rotating pointer, and a recessed
15px fader/level meter with a roughly 13px round handle. The previous Blaze
control used a linear range thumb inside a circle and a noninteractive meter.

The live renderer now shares rotary and fader components across track headers,
the master control and the inspector. They keep native labeled range inputs,
visible keyboard focus, direct pointer capture, Shift fine control, keyboard
steps, Option-click/double-click reset and real readouts. Dragging from an
existing handle retains the grab offset. Meter colors occupy a fixed level
scale, clipped to measured levels; quiet audio does not turn yellow merely
because its meter is short. No inactive track meter is animated artificially.

Track faders have real per-track audition gain, separate from the unchanged
media master volume. A bounded Web Audio GainNode after the existing pan/FX
chain applies the selected saved level with an 8ms ramp. Stem gains are keyed
by job and instrument; unrelated recordings/jobs begin at unity. The app still
auditions one recording at a time, and exported WAV files remain the original
bytes. No multitrack mixing, pan modes, automation or model changes are claimed.
The gain taper and gesture sensitivity are Blaze's, not an assertion about
undisclosed Logic algorithms. Gain state is for the current app session.

Pointer/value updates no longer redraw the arrangement's waveform canvases.
The live suite verifies rotary angle, captured/fine dragging, reset, keyboard
input, actual gain/pan node values, independent master gain, level restoration,
inspector synchronization and zero canvas redraws during knob input. Track
headers use groups with actual selection buttons so sliders are not nested
inside an ARIA option. Five sizes and both appearances remain covered.

Component measurements and scoped contrast pairs are recorded in
`replica/design/logic-audio-controls.json`. Reference/actual UI close-ups are
outside the app at `/workspace/logic-controls/`. Replica, BAMA measurement,
Apple interaction, accessibility and verification guidance were applied;
native macOS-only measurement utilities were not run on this Linux host.
