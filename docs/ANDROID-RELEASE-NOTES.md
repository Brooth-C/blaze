# Blaze Android 0.9.0 preview

A native Android Explore, search and Now Playing interface based on the selected
Blaze discovery design, with original artwork, native icons and light/dark controls.

- Explore offers For you, Music and Videos entry points, with search inside Blaze.
- Search supports All, Songs, Videos, Artists and Playlists filters and supported
  collection pages. Results use provider metadata rather than a bundled music catalogue.
- A shared Media3 player connects audio/video playback, Now Playing, the mini-player
  and queue controls.
- Download actions use the existing durable queue. Completed local files can be
  played or opened in the offline Music Studio.

Discovery and online playback require a network connection and depend on the
bundled, pinned yt-dlp extractor and upstream provider availability. A search
result does not guarantee that a recording can be played or downloaded.

This is a debug-signed preview. Before replacing an older preview, export files
that you want to keep: Android may require removing the old app when its signing
key differs, and uninstalling removes files stored inside Blaze. Physical-device
and OEM background behavior remain incompletely tested.

# Blaze Android 0.8.0 preview

A redesigned Android interface with a focused Music Studio, persistent navigation,
warm light and charcoal dark themes, shared typography and controls, and quieter
library rows. The offline analysis, download and playback engines are unchanged.

- Downloads, History, Library and Studio remain within reach in the bottom navigation.
- The link composer groups format choices and keeps inactive queue controls out of the way.
- Studio gives the current chord, next chord, timeline and transport a clear hierarchy.
- Piano diagrams show readable chord tones; guitar, timing, editing and export remain available.
- Shared native controls include touch feedback, keyboard focus and accessible labels.

This is a debug-signed preview. Before replacing an older preview, export files
that you want to keep: Android may require removing the old app when its signing
key differs, and uninstalling removes files stored inside Blaze. Physical-device
and OEM background behavior remain incompletely tested.

# Blaze Android 0.7.0 preview

Updated home navigation, system light/dark appearance, clearer section selection and preserved offline Studio, downloads and saved-file controls. Built and instrumented on Android API 29 and 35 before publication. Debug-signed preview; physical-phone and OEM background behavior are not comprehensively tested.

# Blaze Android 0.6.0 preview

One app for Downloads, Music Studio and playback, with the proper Blaze logo
and orange theme. Install Blaze-Android-Preview.apk.

- Advanced offline chords default to the same verified ensemble and shared
  frontend/sequence decoder used by Blaze Windows, including extensions/inversions.
- Native Beat This! beat/downbeat detection and conservative automatic meter,
  with persistent manual timing corrections and no invented four-beat lines.
- Smooth beat cells, blank uncertain segments, readable current/next diagrams,
  and a compact phone screen. Extra controls are in Studio options.
- Content/model-addressed caching, cancellation, manual chord editing and exports.

Model and dependency notices are inside the APK. Matching unchanged native
sources: https://github.com/Brooth-C/blaze/releases/download/v4.1.29/Blaze-Android-Native-Sources.tar.gz
SHA256: c2eeadf7bbc8be426ead9248fa69e4a5ce5c490c5484669495e684a3081d226e

Recognition is fallible; broader vocabulary is not a real-song accuracy guarantee.
This is a debug-signed preview; a different signing key can prevent an in-place update.
