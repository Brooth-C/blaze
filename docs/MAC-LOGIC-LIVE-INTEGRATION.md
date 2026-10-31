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
