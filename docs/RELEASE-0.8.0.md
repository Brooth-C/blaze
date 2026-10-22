# Blaze desktop 0.8.0 — discover, listen and keep

Windows, macOS and Linux now bring Android's Explore workflow to a desktop layout. Browse music recommendations, search videos and songs, and move between Explore, Downloads, Library and Music Studio without leaving Blaze.

- Explore shows real provider results and thumbnails. New listeners get general music picks; listening inside Blaze informs later recommendations without a YouTube login.
- Search after a short typing pause, filter the results, and browse supported artists or collections.
- Choose a result to prepare a local playback copy. Progress and cancellation remain available while it prepares; a persistent player then follows you between sections.
- Use Download to send a chosen item to Downloads, choose its format and save a permanent copy. Open in Studio brings the selected playback copy into the existing local analysis workspace.
- Library search, format choices, local imports, chord recognition, corrections, rhythm controls and exports remain available.

Discovery, artwork retrieval and preparation need internet. Provider availability and media quality vary; some items require authentication or cannot be played. Playback preparation can take time and uses a bounded local cache. It is separate from the permanent Downloads library. Listening history stays on this device and can be reset; recommendation requests still send search terms to the provider.

Playback copies use compatible AAC audio or AVC/AAC video up to 720p, with a
512 MiB per-file limit and a two-minute preparation deadline. The cache retains
up to six copies within 1 GiB. Downloads keeps its existing format and resolution
choices. Listening history keeps up to 30 recordings after active listening;
Reset listening history clears that profile.

The Mac build also trials native navigation chrome: macOS 26 can use Apple's Liquid Glass for that control surface, with an older-system material fallback. Studio's notation and timeline retain readable content surfaces. This does not turn the shared web content into native SwiftUI controls.

The recognition models and reviewed decoder assets are unchanged. Chord analysis runs locally; transpose changes notation rather than the recording's pitch. Video codec support still depends on each platform's web view. Browser regressions use controlled metadata and real local media; native package checks exercise AVC/AAC video in the platform webview. These checks do not establish live YouTube availability or physical-device performance.

Windows requires Microsoft Edge WebView2; the app is not Authenticode-signed. Mac requires macOS 13 or newer and remains ad-hoc signed without Apple notarization. Linux is an Ubuntu 22.04 x86_64 desktop preview with the documented GTK/WebKit, FFmpeg and one-time Python installation requirements. Updating preserves the existing media and analysis locations. The Android APK and terminal installers retain their own versions.

Previous binaries remain under their original release tags. The distribution catalog records exact package hashes and native workflow sources when new packages are promoted to Latest.
