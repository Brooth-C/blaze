# Blaze — clarity, control, and craft

Blaze's desktop interface now follows Apple-inspired principles of clarity, immediate feedback and user control. Existing local download, playback, chord recognition, correction and export engines remain in use. This is independent design guidance, not an Apple product or an assertion about what Apple would ship.

## What changed

- Downloads starts with links, an Audio / Video switch and format selection. Playlist settings sit behind More options. Activity shows actual engine progress, errors and completion. Source-quality guidance and the actual storage location remain visible.
- Library uses a Finder-like file list, filename search and All / Audio / Video filters. It lists the backend's latest 200 supported files, not the whole filesystem. Open in Studio selects the real server source.
- Studio puts Import file and Analyze chords beside the heading. Player and practice controls stay together; measured timing and instrument diagrams take priority. Exports and secondary settings remain reachable. Analysis submissions are guarded while the request is pending.
- Scrubbing follows pointer movement continuously with pointer capture and gesture cancellation. Keyboard seeking and playback work before analysis. Dropped Studio files follow the same import path. Media URLs change with selection; media responses disable persistent HTTP caching.
- System, Light and Dark appearances use shared tokens. The authenticated local `/api/appearance` endpoint validates the choice and atomically saves `appearance.json`. The server injects the saved appearance before rendering, independent of changing loopback ports. No online service is involved.
- Command/Control-L focuses download links; Command/Control-F opens Library search; Command/Control-O imports a file. Space toggles Studio playback outside editable/interactive controls. Shortcuts leave modal dialogs alone. Tabs and segmented controls update immediately.
- Relative text units, reduced-motion and reduced-transparency support, selected-state announcements and a scrolling Studio layout for enlarged text improve accessibility. This is not a certification of WCAG compliance.
- Android home follows system light/dark colors with neutral selected sections and orange actions. The separate native Android playback/Studio surfaces retain their existing implementation. Windows and Mac webviews share the redesigned desktop interface.

## Design system

White main surface, cool gray sidebar, charcoal text, fine separators and restrained orange primary actions. Dark mode uses near-black surfaces and lighter text. System fonts establish hierarchy through size, weight, leading and tracking. The sidebar becomes a horizontal task bar on phones.

Downloads uses one composer boundary and an open Activity region. Library stays a file list rather than a card grid. Studio frames the player and real instrument canvases without decorative nested panels. The original Blaze mark remains; outlined SVG controls share one helper. Brief press feedback serves interaction rather than adding constant motion.

## Verification

The real-server Playwright test covers an actual yt-dlp/FFmpeg download from an isolated loopback WAV fixture, submission errors, playlist disclosure, segmented controls, Library search/filtering, file selection, real playback, continuous seeking, actual import, source reload, appearance save/reload, settings, keyboard navigation and enlarged text. A synthetic chord fixture checks timeline rendering, three instrument canvases, transposition and instrument choice; it is not an inference benchmark.

Checked browser sizes: 1536×1024, 1440×960, 780×600, 390×844 and 320×740. Compact keyboard canvases must fit their cards and settings must remain reachable. Review captures live in `docs/assets/0.7.0/`. Browser connector unavailable: local Playwright Chromium was used.

Passed existing suites: 28 regression tests, 20 Mac runtime tests, 10 mobile backend tests, and live-flow, timeline-cell and automatic-rhythm JavaScript suites. Three new tests cover default/corrupt appearance preferences, restart persistence and rejected values preserving the prior choice. See `tests/Blaze-Desktop-UI-Tests.cjs` for the browser test's environment variables; it requires Studio Python dependencies, Playwright, yt-dlp and FFmpeg.

Native release validation uses GitHub runners for Windows WebView2, Linux GTK/WebKit, both Mac architectures and Android API 29/35 emulators. Desktop package checks perform real inference with the shipped models, local downloading, playback, seeking and layout assertions; exact successful build runs and source commits are pinned in [the release catalog](../tools/release_catalog.json). Screenshots are retained with workflow artifacts.

Limits: automated download fixtures use local media rather than external services. Android still needs physical-phone validation. Synthetic chord fixtures verify integration rather than recognition accuracy on annotated songs.

## Concept and render review

Three full-screen concepts were explored for Downloads, Library and Studio. The committed review captures show the implemented interface.

Concepts and browser renders were inspected using `view_image`, including the concept's native 1536×1024 dimensions and 780×600 Studio.

| Comparison | Implementation / deliberate adaptation |
| --- | --- |
| Palette | White, cool gray and charcoal retained. Primary orange darkened for readable white labels. Dark mode extends the same tokens. |
| Layout | Sidebar, composer, Activity, Library list and player/practice/detail hierarchy follow the references. A 216px rail and desktop-sized type replace the concept's enlarged presentation scale. |
| Copy | Main titles, task labels, subtitles and empty-state wording match. Truthful quality guidance, real storage path and global Settings are intentional support additions. |
| Typography | System fonts, relative units, restrained weights and heading tracking; compact controls scale down and enlarged text permits scrolling. |
| Assets/icons | Original Blaze mark retained instead of the generated flame. Shared outlined SVGs and actual piano/guitar canvases replace illustrative assets. |
| Controls | Segmented type/filter controls, progressive playlist options and top-level Studio actions follow the references. Duplicate illustrative audio playback and faux window lights omitted. |
| Data | Real queue/file/source state drives the interface. Unknown timing stays unknown. Synthetic chord data exists only in the browser test. |
| Responsive behavior | Phone task bar, compact details dialog and complete short-window keyboards retain access to controls. |

Above-the-fold copy was checked with the functional deviations above. Material review fixes included instant selection updates, icon/text spacing, compact keyboard space, light-theme diagram labels, source reload behavior and persisted appearance. The screens were visually compared with all three references using these documented platform adaptations; no known clipped primary controls remain in tested layouts.
