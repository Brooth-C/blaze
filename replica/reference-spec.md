# Logic reference to Blaze Studio

## Sources and confidence

Official Apple sources and original observations are in
`docs/MAC-STUDIO-DESIGN.md`. The main-window figure is 1304×932 image pixels,
SHA-256 `92ce7c8615f1d7095b1ec1eda70e6ce41e08e5b162b04b115cce472fa2d5e953`.
The original display scale is unknown; these are not measurements in native
points. Apple figures remain outside the repository and app bundle.

Manual annotations against that figure identify an approximately 1304×824
window crop at (0,54), an 84px-high title/control-bar area, a 408px-wide track
header area, and an 896px arrangement area. Confidence is medium: the rectangles
are annotations, not native frame probes. Dominant pixels in the annotated
regions are #a5a5a5 for the title/control bar, #575757 in track headers and
#2e2e2e in arrangement content. This describes that light-chrome figure, not
Logic's unknown dark-mode colors. Font and icon sizes below are Blaze choices,
not values falsely attributed to image measurement.

A matching 1304×824 Blaze browser capture has an actual 26px fallback title
strip and 56px transport: 82px combined. Native AppKit owns its actual title bar;
the browser's fallback traffic lights are not proof of native window rendering.
Full geometry and color observations are saved in the external QA artifacts.

## Component mapping

| Reference region | Blaze counterpart | Specification / adaptation |
| --- | --- | --- |
| Main window | Existing native shell and Studio | No framework or platform replacement |
| Control bar | `daw-transport` | Compact system-aware chrome, no decorative glass |
| Transport | Existing play/stop/seek/repeat | Real player; unavailable recording omitted |
| LCD | Existing timing/project display | Tabular time, tempo, meter and key; unknown remains unknown |
| Main toolbar | `daw-workflow` | Browse, stems, analysis, details, WAV export, editor toggle |
| Inspector | `daw-inspector` | Existing audition/source/effect controls; 160–300px resize |
| Track headers | Existing real track list | Text selection and mute/audition controls, 24px targets |
| Timeline ruler | Existing source/editor rulers | Project grid retained; finite automatic-meter display |
| Chord arrangement | `daw-harmony` | Four bars by default, proportional source-derived segments |
| Bar ruler | `harmony-bar-ruler` | 24px row; measured bar number or unconfirmed time window |
| Beat subdivisions | `harmony-beat` | Actual detected or corrected timestamps |
| Playhead | Existing cursor and chord cursor | Media clock; transforms; stops updating off-screen |
| Current/selected regions | Borders, text and `aria-current` | No color-only state |
| Hover/pressed | Semantic control states | Contrast increases without changing layout |
| Dividers | Inspector and lower-editor handles | Dedicated gutter, pointer capture, arrow-key adjustment |
| Lower editor | Existing waveform / Chord Guide | Real peaks; explicit chord-derived guide; collapsible |
| Detailed tools | Existing chord-tools panel | Flat graphite; original modes, correction and exports retained |
| Typography | System font | 12px body, 11px metadata, 13px section, 20px chord; LCD labels 10px |
| Icons | Existing Blaze-authored icons/artwork | Consistent existing stroke; no copied Logic assets |
| Scroll/zoom | Native scrollports and supported zoom | 2/4/8-bar groups plus existing waveform zoom/scroll |

## States and intentional differences

Empty: import, then analyse; no fabricated bars or tracks. Processing: existing
analysis/cancel and independent stem progress. Filled: real chord/beat data.
Uncertain: time windows and detected beat marks, never invented meter. Error:
existing visible error and retry paths. Long names: truncate with full context
in existing tooltips. Compact: scrolling track list, optional overlaid inspector,
visible chord strip and a lower editor with a usable waveform height.

Blaze retains one audition player, not Logic's recording, MIDI sequencer,
simultaneous multitrack mixer, sound library or plug-in host. Its time readout
and chord context need more LCD/content space than the particular guide figure.
The main chord strip is a deliberate Blaze-specific region. No whole-screen
pixel-equivalence claim is appropriate for different sessions and capabilities.
