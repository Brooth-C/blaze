# Blaze desktop 0.9.0 — a calmer Mac workspace

The Mac interface moves from a small segmented navigation strip to a native
source-list sidebar and toolbar around the existing WebKit workspace. Explore,
Downloads, Library and Studio have consistent navigation, while search, local
file import and Settings are available from the toolbar.

- Choosing a recording keeps Explore open. A compact player remains available
  while browsing and working in Studio; the expanded player opens on request.
- The Mac content layout uses desktop spacing and type, with playback controls
  designed to fit smaller windows. Studio gives the timeline and notation the
  main workspace and keeps secondary song details separately accessible.
- Native navigation chrome uses system glass on macOS 26 and a system-material
  fallback on older supported Macs. Content surfaces remain readable and respond
  to light, dark and reduced-motion preferences.
- Local file selection uses the native Open panel. The selection stays inside
  the app; there is no HTTP endpoint that accepts arbitrary local file paths.

This is a Mac presentation revision around the shared downloader, recognition
and playback components. It does not replace the content with SwiftUI or add
stem separation. Windows and Linux packages are rebuilt from the same source;
their existing interface and workflows remain unchanged. The Android APK and
terminal installers retain their separate versions.

Discovery, artwork and playback preparation still require internet, and provider
restrictions can prevent playback. Listening history stays on the device;
recommendation requests send search terms to the provider. Chord analysis runs
locally. Transpose changes notation rather than the recording's pitch. Reviewed
models, decoder assets and preparation/cache limits remain unchanged from 0.8.0.

The source release workflows require the Mac presentation-isolation tests,
controlled-metadata browser workflows with real local media, and native packaged
app checks on both Mac architectures. The Apple Silicon package also passes
through the macOS 26 glass and accessibility checks before publication. Browser
checks cover content geometry and interaction; actual AppKit behavior is checked
by the native jobs. These checks do not establish live YouTube availability or
physical-device performance.

Windows requires Microsoft Edge WebView2; the executable is not
Authenticode-signed. Mac requires macOS 13 or newer and remains ad-hoc signed
without Apple notarization. Linux remains an Ubuntu 22.04 x86_64 desktop preview
with the documented GTK/WebKit, FFmpeg and one-time Python installation
requirements. Updates preserve existing media and analysis locations.

Source package releases remain immutable. The distribution catalog moves to a
new Latest release only after native package checks pass and exact package
hashes and workflow provenance are recorded. This source change does not itself
promote the packages to Latest.
