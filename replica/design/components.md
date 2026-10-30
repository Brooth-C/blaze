# Studio component decisions

The governing reference is the public Logic Pro workstation anatomy cited in
recon.md, adapted to Blaze's real audio engine. Preserve the native system font,
neutral panels and semantic track colors; no landing-page template is applied.

- Transport: grouped real playback controls, project grid and output volume.
  Unknown key is shown as a dash. Recording/count-in placeholders are omitted.
- Workflow bar: Browse, project name, Split Stems, Analyse Chords, Chord Tools
  and conditional Save WAV. Labels remain visible; optional panels do not own
  essential actions. Cancel Analysis replaces the unavailable start action.
- Tracks: one actual audio waveform per recording/stem, stable identities,
  keyboard selection, selected-track mute/pan and a real output meter. Colored
  tracks are identities, not claimed confidence or simultaneous mixer output.
- Editor: detailed stereo waveform, fixed amplitude gutter, seek/zoom/reference
  selection. Chord Guide is explicitly derived from recognition, not recovered
  MIDI. Unsupported fade/automation controls are omitted.
- Background task: a short modal setup, followed by independent processing.
  Running details are nonmodal and may be closed without cancelling. Progress
  stays in Studio's stem action and in a task button outside Studio. Completed
  outputs retain their source label when a different recording is selected.
- Errors: next to the responsible action; completion is separate from failures
  and cancellation. Results are not published until all requested WAVs exist.

New workflow tokens: panel #414141, text #ececec, divider #252525, height42px,
gap12px, control height30px. Existing Logic-style theme variables govern the
transport; window appearance follows the user's setting. Numbers use tabular
figures. Motion uses transforms and cached geometry for moving playheads.

Rendered review includes1672x941,1440x900,1024x649 and780x572 browser surfaces.
The native package is separately validated on Apple Silicon/macOS26. Taste's
generic dashboard checks flag the absence of a web-page h1 and small metadata
labels (including hidden Browse/settings DOM). Those are not represented as
clean passes: this surface has a native window/project title and deliberately
compact workstation metadata. Core actions are readable, labelled controls;
viewport-fit, long-name and keyboard tests remain required.
