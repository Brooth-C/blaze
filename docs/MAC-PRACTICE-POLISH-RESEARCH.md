# Practice-only Mac build: research and implementation decisions

## Goals and boundaries

Make finding a song and learning it the complete supported Mac workflow. Remove
Advanced Studio from the stable interface and bundle; stop its development.
Keep anonymous discovery, the persistent media element, existing separation
models, background recognition and saved Practice sessions.

## Explore

The catalogue performed multiple provider searches sequentially, including after
the first batch could populate a general feed. Its cache existed only in memory.
The downloader explicitly loaded macOS system roots, while the image proxy used
OpenSSL's default certificate paths, which can reference the build machine in a
frozen application. This is a confirmed packaging inconsistency; it is not a
claim that every missing thumbnail has the same cause.

Use the existing Mac root-store approach for the proxy, maintaining certificate
and hostname verification and the restricted image/redirect host list. Cache
up to twelve catalogue replies and sixty-four artwork files locally; bound each
image to 1 MiB. Reset removes catalogue caches. Load visible/featured images
eagerly and defer lower rows. Python documents explicit trust-store loading;
Chrome's guidance recommends prioritising visible images rather than marking
every image eager or high priority.

- https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_verify_locations
- https://developer.chrome.com/docs/modern-web-guidance/guides/performance/optimize-image-priority

## Transpose and exports

The existing transpose changed chord diagrams only. Practice now shifts the
actual audio and keeps the displayed chords/key in agreement. For n semitones,
use rate ratio 2^(n/12), resample back to 44.1 kHz and apply reciprocal tempo.
FFmpeg documents `asetrate`, `aresample` and `atempo`; these filters already ship
in Blaze's decoder. No new dependency or alternate separation model is needed.
The worker renders off the HTTP/UI threads, retains bounded results and reuses
completed renders. Pitch changes switch the same player only when audio is ready,
preserving playback position, speed and A–B passage state.

`rubberband` is another documented FFmpeg option, but requires an explicitly
enabled external library. It is not assumed available in Blaze's existing
LGPL decoder. The current implementation must be assessed by real pitch/duration
tests and listening; numerical correctness does not prove musical preference.

Downloads are two independently useful WAV tracks, separately or as a ZIP, as
requested. A mixture would discard their independent practice value.

- https://ffmpeg.org/ffmpeg-filters.html#asetrate
- https://ffmpeg.org/ffmpeg-filters.html#atempo
- https://ffmpeg.org/ffmpeg-filters.html#rubberband

## Chord motion and next improvements

Animate opacity and a small transform only when the active/next chord changes;
keep progress tied to the media clock. Avoid rebuilding cards each frame and
respect Reduced Motion. Web.dev recommends transform/opacity for animation to
avoid layout work. The Practice engine also avoids the removed DAW's background
drawing and multi-track waveform prefetch.

Further work should be guided by device measurements: cold/warm Explore latency,
successful real CDN thumbnails, render time for a full song, frame timing during
separation, and listening on the user's M3/8 GB. Native Apple pitch processing is
a possible later research direction, but is not added without a unified-player
design and audio-quality evidence.

- https://web.dev/articles/animations-guide
