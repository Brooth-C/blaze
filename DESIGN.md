# Blaze Mac Studio

Authority: the user's Logic Pro reference brief, then macOS conventions, with
Blaze's supported workflows and accessibility preserved. This specification is
for the Mac Studio surface, not the Android, Windows or Linux presentations.

- Keep the native AppKit window, sidebar, toolbar and menu behavior.
- The editing surface is opaque graphite in both appearances; chrome follows
  System, Light or Dark. Never apply decorative glass to musical content.
- Use the system font. Body/track labels are 12px, secondary labels 11px,
  section headings 13px and chord symbols 20px. Time values are tabular.
- Use flat, contiguous panels, fine separators, a 4px spacing basis and 3–4px
  region/control corners. Avoid resting card shadows and rounded dashboard tiles.
- `mac-harmony.css` owns the Studio semantic color roles. Machine-readable
  values and contrast pairs are in `replica/design/studio-tokens.json`.
- Arrange transport/LCD, persistent workflow actions, inspector, central chord
  regions and real audio tracks, then the collapsible selected-track editor.
- The chord view starts with four actual bars. Uncertain meter uses explicitly
  named timing windows, retaining detected beat spacing without claiming meter.
- Chord boundaries use the existing `BlazeFlow` model. Never stretch each chord
  into a separate bar or replace real results with a visual demonstration.
- Color identifies actual instrument tracks and the current chord. Selection
  also has borders, labels and accessible state; it never depends on hue alone.
- Separators support pointer capture and arrow keys. Inspector resizing has a
  dedicated divider so it does not obstruct the scrollbar.
- Existing detailed chord tools retain their controls and view modes; diagrams
  inherit their container's palette. Settings remain appearance-aware.
- No new framework, model, service, font dependency or recognition algorithm.

Reference mapping and measurement confidence: `replica/reference-spec.md`.
Implementation scope and verification record: `docs/MAC-UI-REFINEMENT.md`.
