# Current Logic visual replica — appearance-only stage

## Approved scope

The user requested the current Logic Pro appearance, explicitly deferred workflow
work, chose macOS-following appearance and approved visible controls that are not
yet connected to Blaze functions. This implementation is therefore a separate
visual prototype, not a functioning DAW or a replacement for production Studio.

Preview route on the Mac loopback app: `/mac-logic-preview.html`.
A self-contained review artifact is `/workspace/logic12-visual/preview.html`.
No production script imports the preview. The only existing-code change is three
Mac-only static routes and HTML MIME handling. No audio, recognition, separation,
recording, export or user-file behavior is changed.

## Current reference and provenance

Apple's US App Store lookup for Logic Pro id634148309 returned version **12.4**,
released **2026-09-29**. The reference images are the screenshots currently served
by that listing: https://apps.apple.com/us/app/logic-pro/id634148309 .
Lookup evidence, exact image URLs and SHA-256 values are saved outside the app at
`/workspace/mac-studio-replica/latest-logic/`.

The screenshot asset filenames include 2025 dates; their presence on the current
12.4 listing does not prove every pixel was recaptured for version12.4. No claim
of direct access to a running Logic installation is made. Apple images, branded
icons, plug-in artwork and licensed fonts are not bundled or traced.

## Replica mapping

- 56px control layer with grouped window tools, transport, compact musical LCD,
  timing controls, output meter and browser controls.
- 30px contextual strip with Edit/Functions/View, view/tool controls, Snap/Drag
  choices and compact zoom sliders.
- 260px header column at1440px; compact name-above-M/S/R/I and level/pan controls.
  Neutral gray row hierarchy, colored authored instrument symbols and selection.
- Shared ruler, slim chord strip and contiguous colored arrangement regions.
  Illustrative session has nine tracks with varied region lengths.
- Lower Audio Editor with menu strip, time ruler, pale caption, stereo waveform,
  amplitude gutter, selected range and a status strip.
- macOS appearance changes the control chrome using prefers-color-scheme; dark
  editing surfaces remain task content. No decorative glass or generated hero.

Dimensions above are implementation choices based on published screenshot
relationships, not falsely asserted native-point measurements. Native scale and
some details remain uncertain. The sample waveforms/meters are illustrative;
track titles and symbols are Blaze's. There are no engine/API calls.

## Skills actually applied

Replica design/build/diff: extract components, code own assets and layout, compare
shared regions at matched width. Image-to-code: image analysis and faithful
translation; its marketing-page generation defaults are superseded by the user's
actual-app reference. Apple/BAMA guidance supplies system typography, native
control density and macOS appearance behavior. Verification-before-completion:
fresh rendered QA before pass claims. No subagents, external AI, paid APIs or
proprietary binary inspection.

## Verification and evidence

`tests/Blaze-Mac-Logic-Visual-Tests.cjs` renders the actual preview source in light
and dark at1440×900,1280×800 and1024×700. It verifies nine tracks, selection/mute
appearance, menu dismissal, editor disclosure, canvas pixels and viewport fit,
with no page errors and no production API calls. Minimum design width is980px.
This is a desktop appearance study, not mobile UI or native macOS validation.

Existing Mac Presentation4 and Runtime22 tests pass. JavaScript syntax, Ruff
F/E9 and whitespace checks pass. No production workflow or model-quality claim.

Review artifacts in `/workspace/logic12-visual/`: six rendered screenshots,
reference-comparison.png, matched control-bar crops/diff, qa.log and runtime.log.
The full comparison intentionally shows a different lower editor and no synth
plug-in overlay, matching the user's arrangement + waveform-editor choice.
The edge-map tool does not establish whole-application pixel parity.

The UI is not published as a new stable Mac release. Functional hookup and native
Mac integration are deferred to the next phase the user explicitly separated.
