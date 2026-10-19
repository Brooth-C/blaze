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
