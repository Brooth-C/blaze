# Mac Studio design

Studio follows the workstation structure documented in Apple's Logic Pro for
Mac user guide. The earlier generated Blaze concept is no longer its design
reference. This is a visual and interaction update to Blaze's audio/stem
workspace, with its existing player, separation and chord-analysis engines.

## Sources and observations

Reviewed on 2026-10-28:

| Official source | Observed pattern | Blaze implementation |
| --- | --- | --- |
| [Main window](https://support.apple.com/guide/logicpro/main-window-interface-lgcpe9cc403a/mac) | Compact control bar, centered dark LCD, show/hide controls and master output | Appearance-aware control chrome, actual transport/project controls and live output meter |
| [Tracks area](https://support.apple.com/guide/logicpro/tracks-area-interface-lgcpe9cc3f60/mac) | Flat gray track headers, colored index strips, compact controls and saturated regions | Separate track-selection buttons and mixer controls, real saved-stem waveforms, slim color strips |
| [Audio Track Editor](https://support.apple.com/guide/logicpro/audio-track-editor-interface-lgcpe9cc446b/mac) | Numbered ruler, pale region caption, blue-gray stereo waveform, fixed amplitude gutter | Independent lower ruler and caption, normalized real peaks, viewport-fixed L/R amplitude scale |
| [Control bar](https://support.apple.com/guide/logicpro/customize-the-control-bar-lgcp5bdd6d9d/mac) | Controls grouped around transport and LCD | Compact panel toggles, transport, project timing and output groups |
| [Inspector](https://support.apple.com/guide/logicpro/inspector-interface-lgcpe9cc3b1d/mac) | Selection-dependent Region/Track controls and channel strips | Region/Track disclosures, real audition EQ/compression, pan, volume and meters |

The guide figures demonstrate light system chrome over a dark workspace. They
do not establish Logic's dark-mode palette. Blaze follows the user's appearance
for window/control chrome and retains dark editing surfaces in both appearances.
No glass is applied to the track or waveform content.

Replica supplied the screen/component and behavior inventory. BAMA's
design-from-app guidance supplied the measurement/review process. REA 6.8.0
successfully listed the owned browser's Apple page and captured its visible
viewport through CDP; the PNG bytes were checked against its reported SHA-256.
This is public web-reference evidence, not execution or decompilation of the
native Logic application. Detailed UI observations above come from the guide
figures, which were separately opened and reviewed. Apple screenshots and the
research capture stay outside the repository and application bundle.

## Layout and behavior

- The optional Library starts closed. Opening it provides real session tracks
  with family and text filters; it does not advertise unavailable sound patches.
- The wide layout uses a 210 px Inspector and 310 px track-header column. These
  are Blaze layout choices based on the documented anatomy, not claimed exact
  Logic measurements. Smaller windows adapt the columns and expose panels as
  overlays while keeping transport and waveform controls available.
- The lower editor has its own 27 px ruler, 23 px region caption and a fixed
  58 px stereo amplitude gutter (43 px in compact windows). Zoom scrolls audio
  content while leaving the gutter visible.
- Numbered rulers, grid lines, cycle placement and beat snapping share project
  tempo and time-signature units. The gold cycle strip appears only in the
  arrangement ruler.
- Selecting stems preserves keyboard focus unless the user has moved to another
  control. Space on a selection button selects the track. Empty-space Space
  retains the existing play/pause shortcut.
- Inspector and track-row mute/pan controls share state. Loading and errors
  remain visible in compact windows. Playback options support keyboard dismissal
  and return focus to their opening button.

## Scope

Blaze retains one persistent audition player. Displaying saved instrument tracks
does not introduce simultaneous multitrack mixing, recording, a sampler, MIDI
sequencing or a plug-in host. The MIDI guide still comes from chord recognition.
The Inspector's effects operate on audition playback; Save WAV exports the saved
stem unchanged. Unsupported reference controls remain disabled or are omitted.
Original Blaze instrument artwork and authored icons are used; no Logic assets
or binaries are bundled. Android, Windows and Linux presentation is unchanged.

## Verification

Browser regression checks use real local WAV files and a controlled separator;
they cover waveform pixels, selection/export, playback/seek, zoom/scroll,
appearance, panel resizing, fixed ruler/gutter layout, keyboard/focus, mixer
state, visible request failures and unrelated-import invalidation. This does not
measure separation quality. Actual AppKit/WebKit packaging and appearance checks
run on Apple Silicon with macOS 26 only.
