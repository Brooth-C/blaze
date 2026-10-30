# Blaze Mac Studio: workflow reconstruction

Scope: the Mac Studio audio/stem workspace, using Apple's public Logic Pro
documentation as a layout and interaction reference. No Logic source code,
licensed assets, recording engine, plug-ins or proprietary content are copied.

Sources: [Main window](https://support.apple.com/guide/logicpro/main-window-interface-lgcpe9cc403a/mac),
[Tracks area](https://support.apple.com/guide/logicpro/tracks-area-interface-lgcpe9cc3f60/mac),
[Audio editor](https://support.apple.com/guide/logicpro/audio-track-editor-interface-lgcpe9cc446b/mac).
Reference images remain outside the repository and bundle. Existing detailed
observations are in docs/MAC-STUDIO-DESIGN.md.

## Screens and flows

- S01 Explore: search, loading, results, empty, provider error and retry.
- S02 Studio: real track lanes, selected-track inspector and waveform editor;
  empty, decoding, ready, long names and compact window states.
- S03 Separation task: setup, running, cancellation, failure and completed
  tracks. Running details are a nonmodal panel; progress remains discoverable.
- S04 Chord tools: analysis, diagrams, corrections and exports; independent of
  separation and backed by the original recognition engine.

F01 Search -> choose recording -> Studio -> play/seek -> save a completed file.
F02 Studio -> Split Stems -> choose mode -> background processing -> continue
browsing or analysing -> reopen task -> select a completed stem -> Save WAV.
F03 Studio -> Analyse Chords -> Chord Tools -> review/correct -> export analysis.

## Governing design decisions

Keep neutral, flat editing surfaces, a compact transport and centered LCD,
aligned track controls, colored audio lanes and a lower stereo editor. The
Studio action bar always exposes Browse, Split Stems, Analyse Chords, Chord Tools
and, for a selected saved stem, Save WAV. Panels are optional; core actions are
not hidden inside them. An unknown key stays unknown until detected or set.

BAMA UX guidance selects a nonmodal panel for running work. Anthropic frontend
design and Taste app-screen guidance keep the user's workstation reference and
real data ahead of generic page layouts. Baseline UI keeps consistent existing
primitives and keyboard access. Motion-performance guidance moves playheads via
transforms with cached geometry. Lane colors distinguish actual tracks, an
intentional exception to generic dashboard hue limits. Native system typography
is retained; no web font or landing-page imagery is added.

## Data ownership and constraints

The current recording, chord worker and separation job have distinct ownership.
Separation pins its input and copies it on its worker before inference. It never
writes the chord worker's busy/progress state. Source revision and canonical
saved-file identity protect waveform/selection ownership. A second separation
must wait or cancel the first. Cancelling analysis does not cancel separation.

Blaze auditions one track at a time. Only its actual playing output is metered.
Track lanes always contain audio waveforms; chord-derived notes appear only in
the explicitly named Chord Guide. Recording, MIDI sequencing and unavailable
editing controls are omitted. Export saves the original completed WAV.
