# Skill execution report — Studio refinement

Catalogue: /workspace/shared/agent-skills (406 verified skill entries). This report
records guidance actually read/applied and commands actually run. A skill is not
a separate model or automatically executed agent. External QA artifacts below
live in /workspace/mac-ui-refinement; application code and design docs are in
this repository. No subagents, hooks, external model gateways or paid APIs ran.

| Skill | Stage | Applied instruction / actual action | Files / evidence |
| --- | --- | --- | --- |
| baseline-ui | Design/refinement | Compact native conventions, semantic controls and focus; retain existing plain JS stack | mac-harmony.css/js |
| design-taste-frontend | Design/QA | Read app-screen references; reject marketing shell; actual CDP app probes at three widths | taste-audit/report.json; components.md |
| impeccable | Audit/refinement | Context command; Operate/polish/craft floor; one earlier mechanical scan returned no findings; later drawer changes manually reviewed | MAC-UI-REFINEMENT.md; mac-harmony.css |
| improve-ui | Audit | Evidence-based high-impact issue selection; explicit implementation request overrides read-only handoff | MAC-UI-REFINEMENT.md |
| frontend-design | Design | Domain-specific density, hierarchy and real interaction instead of generic cards | mac-harmony.css; DESIGN.md |
| make-interfaces-feel-better | Refinement | Aligned control geometry, optical hierarchy, honest state feedback | mac-harmony.css/js |
| ui-ux-pro-max | Research/design | Ran system query, rejected unrelated marketing palette; scoped UX query for compact keyboard controls | MAC-UI-REFINEMENT.md |
| design-system | Tokens | Semantic colors/type/space and reusable states | studio-tokens.json; mac-harmony.css |
| frontend-design-direction | Contract/QA | Product-specific evidence contract, content states and local checker | design-evidence.json; reference-spec.md |
| frontend-ui-engineering | Implementation | Existing DOM composition, responsive constraints and accessible state semantics | mac-harmony.js/css |
| accessibility | Implementation/QA | Named controls, focus, readable text, keyboard interaction and honest limits | mac-harmony.js/css; Harmony UI test |
| fixing-accessibility | Refinement | aria-current, bounded separator values, announcement only when chord changes | mac-harmony.js |
| fixing-motion-performance | Performance | Cached group DOM, guarded text updates, transform playheads, offscreen/paused scheduling | mac-harmony.js; performance.json |
| browser-qa | QA | Rendered local fixture flows, primary bounds and regression evidence | six browser suites; after captures |
| playwright-cli | Visual QA | Actual open/resize/run-code/screenshots with existing Chromium; workspace cache/config workaround | blaze-matched-light.png; chord-tools-light.png |
| web-design-guidelines | Review | Latest guidance fetched; focus, overflow, state and labeling review | web-guidelines.md; Harmony test |
| verification-before-completion | Verification | Fresh command results before pass claims; native evidence kept separate | final logs; verification report |
| apple-design | Design | Direct manipulation, restrained materials and existing platform controls | mac-harmony.css/js |
| bama-mac-design | Reference/design | Desktop density and meaningful hierarchy; no glass editing canvas | DESIGN.md; reference-spec.md |
| bama-ux-design | Workflow | Context/actions, state feedback and keyboard alternatives | components.md; Harmony test |
| bama-layout-grid | Layout | Grid alignment, panel relations and bounded resizing; no incompatible Swift helper | mac-harmony.css |
| bama-design-from-app | Reference/QA | Annotated screenshot geometry with explicit confidence; DOM and Pillow alternative to unavailable native frame probes | reference-measurements.json; reference-spec.md |
| bama-design-system | Tokens | Semantic roles adapted to existing CSS architecture | studio-tokens.json |
| bama-design-kit | Components | Control/type/selection hierarchy adapted to current framework, no Swift gallery | components.md; mac-harmony.css |
| bama-test-mac-app | QA | Layered pure/browser/native boundaries adapted to Python/AppKit; no SwiftTesting claim | test-plan.md; Mac package smoke assertions |
| replica-recon | Reference | Official source inventory and capability mapping | recon.md; reference-spec.md |
| replica-design | Tokens/reference | Component extraction and actual bundled contrast checker: 13 AA pairs | studio-tokens.json; contrast.json |
| replica-architect | Architecture | Adapt UI to existing server/player/timing model; no stack/backend replacement | architecture.md |
| replica-build | Implementation | Incremental real components and documented safe corrections | mac-harmony.js/css; bugs.md |
| replica-diff | Comparison | Actual image layout tool on matched-width control bars; honest partly result, not full-app parity | control-bar-matched-diff.json; side-by-side |
| replica-test | QA | Local real-flow tests and reproduced bugs; existing test conventions retained | test-plan.md; bugs.md; Harmony UI test |
| change-impact | Inspection | Trace static assets, shared palette consumers and persistent-player contract | architecture.md; shared desktop regressions |
| code-review-and-quality | Review | Focused self-review of correctness, scope, interaction, performance and testing; no independent-agent review claim | source diff; verification report |

## Considered but skipped or limited

- interface-design: absent; frontend-design fallback used.
- taste / taste-application: actual music/video-generation workflows do not apply.
- reverse-engineer-anything: no binary evidence required; no proprietary inspection.
- image-to-code: overlapping path not activated; official screenshot mapping handled by Replica/BAMA.
- bama-clone: read; no local Logic installation or native inspection available. Public documentation substituted; no exhaustive runtime walk claimed.
- bama-research: read; market/review/delegation tracks unnecessary for the explicit reference target.
- liquid-glass-design: iOS/SwiftUI-specific; no glass in the DAW editing surface.
- frontend-patterns, React/Vite/SwiftUI/concurrency templates: incompatible with this existing plain JS + Python/AppKit application.
- component-canvas: read; separate exploration surface not needed for the production workspace.
- bama-build-and-verify / bama-improve-loop: native Swift helper/automatic backlog instructions are inapplicable; current package CI and manual scoped iterations used instead.
- using-agent-skills: scoped discovery followed; broad routing/hooks not enabled.
- skill-stocktake: skill-quality audit is a different task; no redundant catalogue-wide audit.
- repo-scan: inspected bootstrap purpose; not a source auditor for this task.
- planning-and-task-breakdown: its well-defined-spec exception applies; the user supplied execution milestones.
- create-design-md: separate reconstruction workflow not activated; DESIGN.md authored through reference/architecture work.
- code-simplification: considered; no unrelated refactor needed.
- desloppify: available and used in earlier work; not rerun as visual authority or claimed as a new exhaustive scan here.
- Generic onboarding, brief/brand/user-story routers, marketing, orchestration and unrelated platform skills were not activated. Existing scope and identity were already explicit.

## Evidence limits

Native VoiceOver, physical-device audio/frame profiling and a local read-only
Logic session were unavailable. Browser tests and token contrast are partial
accessibility evidence, not complete certification. Taste probes still report
small text in existing/hidden app content, a visually hidden h1 as no-title, and
font-count warnings; these are recorded rather than silently marked clean.
The user-approved desktop density retains 10px LCD captions. Reference artwork
stays outside app/repository assets. No screenshot was uploaded to an external
research provider.
