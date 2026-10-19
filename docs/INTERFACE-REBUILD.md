# Blaze interface rebuild

> Superseded by the Apple-inspired interface pass. See [APPLE-DESIGN.md](APPLE-DESIGN.md) for current behavior, screenshots and verification.

The desktop webview now has three distinct workspaces: Downloads, Library and Music Studio. Android's home screen separates Downloads, History and Library. Existing download, playback, recognition, export and storage engines remain in use.

## Interface decisions

- Graphite background `#10131c`, surfaces `#171d27`, orange `#ff8c42`, muted text `#a8b1c1`; system sans typography, 8–12px corners, restrained outlined icons.
- Downloads opens by default. A source supplied at startup opens Studio. Link entry, format controls and submission form one composer; queue status is a separate list.
- Library lists the backend's most recent 200 supported files, with filename search and All / Audio / Video filters. Opening a file selects the existing server source and enters Studio. Search is limited to the backend list, not the whole filesystem.
- Studio keeps playback, waveform, measured chord timing, three instrument diagrams, transposition, A–B looping, export and correction settings. A normal progress line supports seeking before analysis. No waveform, chord or tempo is invented for an unanalysed file.
- File changes clear old analysis and use a distinct media URL revision so browser media caching cannot retain the prior source's duration. File import disables repeat uploads while active.
- Tabs support arrow keys, Home and End, selected-state announcements and focus indicators. Compact Studio windows move video/details into a dialog. Phone widths use a horizontal task bar and a stacked composer.
- Android retains existing queue, retry, export and playback behavior; the download composer is hidden in History and Library. Section selection follows restored state and retry transitions.

## Verification

`tests/Blaze-Desktop-UI-Tests.cjs` starts the real authenticated loopback server in a temporary directory. It generates a 12-second WAV and a filename-only video fixture for filtering, then exercises empty/invalid link errors, format controls, library filters/search, source selection, real WAV playback, pointer seeking, settings, actual file import, synthetic chord rendering/transposition, keyboard navigation and 1440×960 / 780×600 / 390×844 layouts. The chord UI fixture is synthetic and does not claim model inference. It deletes its temporary server state on exit. Set `BLAZE_UI_SCREENSHOTS` for optional review screenshots outside the repository.

Run with installed Studio Python dependencies and Playwright Chromium:

```sh
BLAZE_TEST_PYTHON=/path/to/python \
PLAYWRIGHT_MODULE=/path/to/playwright \
PLAYWRIGHT_CHROMIUM=/path/to/chrome \
node tests/Blaze-Desktop-UI-Tests.cjs
```

Passed: desktop browser integration test; 28 existing regression tests; 20 Mac runtime tests; 10 mobile backend tests; live-flow, timeline-cell and automatic-rhythm JavaScript suites; JavaScript syntax and whitespace checks.

Limits: this Linux environment has no native Cocoa/Windows webview verification, Android SDK/emulator, or packaged recognition weights. Native Android compilation was attempted but Gradle distribution retrieval failed with connection refused. New chord inference, external website downloads and Android visual behavior therefore have not been verified in this task. Existing timing suites test the unchanged flow engine. Native packaging and emulator checks remain necessary before a release.

## Visual review

Concept: `local design reference: exec-02a5e533-c8ff-4032-bf67-fc418b9536a6.png` (a 1536×1024 composite containing Downloads, Library and Studio). Rendered screens were captured with local Playwright because the Browser connector was unavailable. Both the concept and browser screenshots were inspected using `view_image`; the main screen was checked at 1440×960, plus 780×600 and phone sizes. The composite is compared by screen region, not as one native app viewport.

| Comparison | Render result / decision |
| --- | --- |
| Navigation | Left rail, same three tasks and warm orange selected state; horizontal on phones. |
| Palette | Graphite and orange tokens preserved; removed earlier teal/gradient overrides. |
| Hierarchy | Large Downloads title, supporting line, link composer, then queue; Library keeps search/filter above the file list. |
| Controls and icons | Consistent outlined navigation/folder icons and orange primary action; replaced platform-dependent transport emoji with SVG. |
| Spacing and containers | Composer and queue use one border each; file rows remain a list. Compact controls stay visible at 780×600. |
| Real media | Existing Blaze mark retained; source-dependent progress, preview and diagrams replace the concept's illustrative example data. |

Intentional copy/layout deviations: retained required practice controls absent from the small Studio concept panel; omitted invented artist/title metadata and an unsupported new-window action; retained truthful source-quality guidance and added the actual link limit, storage path and file count. The empty queue omits a decorative document icon. Browser screenshots show the actual source state rather than the concept's illustrative populated Studio. Primary Downloads/Library headings, navigation, primary action and empty-state wording match the concept; additions above are deliberate usability/support details. Material defects fixed during review included the missing development logo asset, transport emoji rendering, stale source metadata and compact-window control clipping. The implemented screens were visually verified against the concept with these documented functional deviations.
