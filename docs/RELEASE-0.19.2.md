# Blaze for Mac 0.19.2

This build focuses on finding music and practising songs.

- Advanced Studio is removed from the Mac interface, asset routes and application
  bundle. Its historical source remains archived in the repository; development
  is paused. Practice uses a smaller independent playback/waveform adapter.
- Explore's image proxy loads the Mac's trusted root certificates, matching the
  downloader's trust setup. Visible artwork loads eagerly, offscreen artwork
  loads lazily, and bounded local artwork/catalogue caches speed up reopening.
- General recommendations can appear after the first useful provider result
  batch. Anonymous recommendations still use real YouTube results and local
  listening history; no YouTube login is required.
- Practice gains −12 to +12 semitone transpose. Audio is prepared locally in the
  background, playback tempo is preserved, and chord/key labels follow the pitch.
  Saved Practice sessions remember transpose along with speed, passage and mode.
- Download Piano WAV, Backing WAV or both separate WAV files in a ZIP. Downloads
  use the selected transpose. Original-key WAV exports preserve the saved bytes.
- Chord changes have a short fade/slide and a passage progress indicator.
  Reduced Motion suppresses the animated chord transition.

No separation model or GPU defaults are changed. Transpose is a cached local
render, rather than an instantaneous live audio effect. Rendering/export is
bounded to one worker, 512 MiB per WAV and four retained export folders; oversized
recordings report an error. Other platform releases are unchanged.
