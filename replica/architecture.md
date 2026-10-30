# Existing Mac UI architecture

The current Python/AppKit shell and authenticated loopback server remain. There
is no stack selection, database migration, cloud account or new API contract.

`server.py` serves two additional static Mac assets after `mac-studio.js`.
The packager already copies the web directory. Other platform documents do not
load these assets. `mac-harmony.js` owns the chord presentation and panel-size
controls; `mac-harmony.css` owns their semantic visual roles.

The component reads existing `result`, `flowMap`, source identity and media time.
It uses `BlazeFlow.state`, measure regions and the existing `seek`/analysis
controls. Recognition, timing inference, persistence, authorization, WAV
generation and separation ownership are unchanged. The same media element is
used throughout.

One existing presentation defect is corrected: automatically inferred beat
counts with an unknown denominator no longer produce `4/null` or an infinite
project ruler. The display says `4 beats`; it does not invent a denominator.

Diagram colors now resolve from their canvas container. The default palette
still inherits from the document on other platforms.

Verification: existing content/Studio/stem browser flows, dedicated musical
subdivision/follow/resize checks, shared desktop regression and actual packaged
AppKit/WebKit checks on Apple Silicon macOS 26. Native VoiceOver and physical
device audio/frame profiling are separate manual limitations.
