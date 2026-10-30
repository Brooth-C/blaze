# Mac Studio refinement

## Audit and direction

Base: stable 0.16.0, main 03cc2cf. The Mac app is a Python/AppKit shell with
an authenticated local HTML/CSS/JavaScript workspace. Existing analysis,
timing, playback, exports and background separation remain authoritative.
The newer Studio brief takes priority over an unrelated Explore redesign.

Before captures and rendered baseline checks are stored outside the repository
under `/workspace/mac-ui-refinement/before`. Both existing Mac content and
Studio browser suites pass on the baseline. These are browser checks, not
native macOS evidence.

The governing visual reference is the official Logic main-window, Tracks area
and Audio Track Editor documentation linked in MAC-STUDIO-DESIGN.md. Its dense
workstation structure, flat controls and dark content are retained. Blaze uses
its own artwork and icons. No fake recording, instrument patches or tracks are
introduced.

Five highest-impact changes:

1. Make real chord results visible in the main workspace, with four-bar groups,
   proportional regions and current/next context; keep unknown timing honest.
2. Separate transport, source tracks, chord results and the waveform editor with
   a restrained graphite token system instead of overlapping neutral styles.
3. Improve small-label contrast, control states and keyboard focus without
   replacing compact desktop controls with large web buttons.
4. Let users resize the inspector and lower editor, and collapse the lower
   editor when they need more arrangement space.
5. Keep empty, processing, error, long-title and compact-window states usable;
   preserve cancellation, source selection, waveform/export and the shared player.

## Design plan

Archetype: existing sidebar media app with a full-window Studio workspace.
Information architecture: Explore, Downloads, Library and Studio remain intact.
Command map: existing transport and app shortcuts retain their meanings; panel
separators add arrow-key resizing, and all new controls have accessible names.
Empty state: import a recording, then analyse chords; no fabricated regions.
Feeling: focused, legible and familiar during a long music session.

Palette roles: workspace #242426, panel #303033, raised #3b3b3f, line #1b1b1e,
text #f2f2f4, secondary #c1c1c7. Blaze orange marks the current chord; instrument
colors identify real saved tracks. Native window/control appearance remains
system-aware. Use the system font, a 4px spacing scale and tabular time values.
No decorative motion or glass on the editing canvas.

## Skills and applicability

Read and apply baseline-ui, design-taste-frontend's app-screen guidance,
impeccable (context, Operate/polish and craft floor), frontend-design,
make-interfaces-feel-better, ui-ux-pro-max, design-system,
frontend-design-direction, frontend-ui-engineering, accessibility,
fixing-motion-performance, browser-qa, web-design-guidelines,
verification-before-completion, apple-design and BAMA Mac/UX/grid guidance.
Improve-ui supplies the evidence-based audit lens; the user's explicit request
to implement takes priority over its read-only handoff workflow.

Skipped: interface-design is absent; frontend-design is its requested fallback.
The installed taste and taste-application are video-generation/editing skills.
Frontend-patterns is React/Next-specific; this app remains plain JavaScript.
Component-canvas is a separate component-exploration deliverable, not needed for
this screen refinement. Liquid-glass-design targets iOS SwiftUI; no canvas glass
or framework migration is appropriate. BAMA's SwiftUI template scripts cannot
validate this Python app; use its layered test principles with existing browser
and actual macOS 26 package checks. Native VoiceOver and physical frame-rate
measurements require a real Mac and must not be inferred from browser checks.

The UI/UX Pro Max system query returned marketing-page guidance inappropriate
to a DAW and was rejected. A scoped desktop-control/focus query returned applicable
keyboard-state guidance. Preserve the established Mac identity rather than
persisting an unrelated generated palette or dealing a random replacement shell.

## Implemented and verified

The latest MASTER UI replication brief governs this patch. Actual source,
reference mapping, interaction checks and evidence are documented in
[MAC-UI-VERIFICATION.md](MAC-UI-VERIFICATION.md) and the per-skill execution
ledger [MAC-UI-SKILLS.md](MAC-UI-SKILLS.md). Reference measurement confidence
is explicit in [reference-spec.md](../replica/reference-spec.md). The final
code preserves the existing engine and makes the real chord timeline primary.
