# Android interface

Blaze uses a restrained native Android interface informed by the installed Apple
Design, Design System and Accessibility guidance. It is an independent design;
platform navigation, system fonts, document pickers and accessibility remain Android.

The shared tokens live in `res/values/colors.xml` and `res/values-night/colors.xml`.
`BlazeUi` owns typography, surfaces, icons and control states. Light mode combines
warm off-white with white grouped surfaces; dark mode uses charcoal rather than
the former blue palette. Orange identifies meaningful actions and the current chord.

Primary content has 20–24dp side margins. Spacing follows a 4dp rhythm; grouped
surfaces use 22dp corners, controls 15dp. Text uses the system sans-serif family,
medium-weight headings and scaled sp units. Standard controls have at least 48dp
touch targets, with ripple feedback and visible keyboard focus. Text and action
contrast are checked in both system themes by Android instrumentation.

Downloads focuses on one link composer. Persistent navigation exposes Downloads,
History, Library and a Studio import action. Queue controls appear when relevant.
Completed files have a clear Play action; More holds sharing, Studio, export and
deletion. Destructive operations retain their existing confirmation.

Studio centers the chord timeline and current/next diagrams above a persistent
transport. Compact phones and larger text move instrument choices into Options;
landscape uses separate timeline and diagram columns. A named playback container
contract replaces assumptions about child indices. Timing, corrections and exports
continue to use the existing offline engines.

The interface avoids decorative blur and compulsory animated transitions. Native
pressed/focus feedback remains available with system animations disabled. Custom
timeline graphics expose chord seek actions to accessibility services and keyboard
navigation. Diagram note descriptions complement the visual piano/guitar drawings.

Validation includes the existing playback, seek, fullscreen, analysis and export
regressions, plus navigation restoration, light/dark contrast and visible controls.
Emulator screenshots cover home, library/history, Studio portrait/landscape and
1.5× text, plus a scrollable workspace at 2× text. Emulator coverage does not establish physical-device/OEM compatibility
or a complete accessibility certification.
