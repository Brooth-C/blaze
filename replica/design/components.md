# Studio component decisions

The governing specification is [reference-spec.md](../reference-spec.md).
The existing Python/AppKit + WebKit stack, engine and persistent audition player remain.

- Control bar: system-aware title/transport, compact LCD with tabular values.
  Only supported controls. Unknown automatic denominator reads “4 beats”.
- Workflow: Browse, source name, stems, analysis/cancel, Chord Tools, WAV export,
  Editor. Primary actions remain available outside optional panels.
- Inspector: real source/audition/effect controls; 160–300px pointer/keyboard resize.
  A dedicated 4px gutter preserves its scrollbar. Narrow windows use the existing overlay.
- Chord timeline: default four measured bars; proportional region widths for every
  chord change; 24px ruler, 72px lane (56px compact), 20px symbols. Actual detected
  beats remain visible even with unknown meter. Unknown meter uses time windows.
  Click/Enter seeks; context menu opens the existing correction action.
- Navigation: previous/next groups, Follow and 2/4/8 bars; horizontal scroll when
  the minimum 110px bar width (100px compact) exceeds the available space.
- Tracks: actual authorised recording/stem waveforms, persistent source identity,
  24px M/S controls. Colors identify tracks, not confidence or simultaneous mixing.
- Editor: existing stereo peaks, seek/zoom/selection and chord-derived guide.
  180px minimum height; pointer/keyboard resize and collapse. No fake MIDI editor.
- Details: existing Chord Tools drawer, mode/anticipation/correction/voicings and
  exports, restyled with inherited graphite canvas colors and flat separators.
- Background work: existing independent stem progress, nonmodal details, explicit
  cancellation, real output export; chord worker remains separate.

Semantic tokens: [studio-tokens.json](studio-tokens.json), implemented in
mac-harmony.css. System font; 12px body / 11px metadata / 13px section / 20px
chords; 10px compact LCD captions. 4px spacing scale; 4px control and 3px region
radii. Current chord has orange fill, a distinct border and aria-current;
keyboard focus is visible. Live announcements change at chord boundaries only.

Playback uses the existing media clock, cached group DOM and transform playheads.
No decorative animation. Frame scheduling stops when paused, offscreen or hidden.
No copied Apple code, assets, instrument patches or branding.
