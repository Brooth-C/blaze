# Blaze for Mac 0.19.5

Live search, reliable WAV exports and lower processing overhead for learning songs.

- Search updates while typing and uses larger video thumbnails, duration badges,
  channel details and filter chips. Repeated queries reuse recent results, and
  loading more results preserves existing rows and decoded artwork. Stale results
  cannot replace a newer selection or an imported recording.
- YouTube playback verifies the selected recording ID before using downloaded
  media. Search and artwork use the Mac's certificate roots, with bounded waits,
  shared artwork requests and memory caching.
- Piano, Backing and paired separate-WAV exports use the native Save dialog.
  Downloads can optionally change audio pitch independently of chord transpose.
- Practice uses one playback animation loop and change notifications for waveform
  updates. Chords remain pinned, with reduced-motion support and clearer controls.
- Chord analysis avoids repeated spectral, probability and naming work. Separation
  avoids unnecessary PCM, spectrogram and output-buffer copies, and packs WAV
  data more efficiently. Idle browsing no longer repeatedly scans the library.

The existing model weights, inference precision, sample rates, chunk sizes and
separation overlap settings are retained. CPU comparisons verify the optimized
steps against their original numerical precision, including byte-identical complete
controlled piano/backing WAV exports. Component benchmarks are not claims of whole-song speed on an M3 Mac.

Advanced Studio remains excluded. This release builds Apple Silicon only;
existing Windows, Linux, Android and Intel downloads remain available unchanged.
