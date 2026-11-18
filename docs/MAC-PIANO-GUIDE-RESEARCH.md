# Piano practice chord timing

Research and implementation: November 18, 2026.

The user reports that detected changes can be valid while their presentation
is unsuitable for playing piano. This change addresses the practice guide;
it does not claim to transcribe a pianist's full accompaniment arrangement.

## Findings

[Moises documents synchronized chord views and easy/medium/advanced presentation](https://help.moises.ai/hc/en-us/articles/6569274648220-How-do-I-use-Chord-Detection).
[Chordify's guide](https://support.chordify.net/hc/en-us/articles/360002148497-How-to-use-Chordify-on-Desktop)
uses visible beat positions and bar boundaries to support playing along, and
[its simplification feature](https://chordify.net/pages/play-along-your-way/)
distinguishes easier accompaniment from the full detected chord detail.

[Research on piano sight-reading](https://www.nature.com/articles/s41598-019-54364-y)
supports the importance of anticipation, with reading ahead influenced by
tempo and musical complexity. It does not establish a universal two-beat
preview or a validated suppression threshold for this application.

The useful design distinction is between recognized harmony and guidance for
playing it. A preparation cue can appear before the next change while the
current chord remains synchronized to the recording.

## Implemented behavior

- A compact Piano phrasing / Detected control changes presentation only.
- Piano phrasing holds the surrounding harmony across a brief A–B–A event
  when B lasts no more than 0.24 seconds or 0.45 of the local detected beat,
  whichever is shorter. Both surrounding A events need meaningful duration.
  These conservative limits are product heuristics, not published model
  accuracy claims. The detected view retains the original events.
- Real transitions, offbeat timing, silence, gaps and manually edited events
  are preserved. The song is not globally quantized or reduced to triads.
- The next chord gets a countdown and a preparation indicator within two
  beats. Without a measured beat interval, it uses remaining playback seconds.
  Slower playback adjusts the wall-clock countdown; measured beat spacing is
  interpolated locally instead of assuming a constant song tempo.
- The current chord changes at its guide boundary. Preparation does not label
  a future chord as already sounding. Loop cues follow the chosen passage
  rather than a chord beyond the loop end.
- The guide can work before rhythm analysis completes. It adds no neural
  inference, audio processing or model download. Known-event and beat arrays
  are cached; playback lookup uses binary search.
- Original analysis results, exports, model precision, audio and final
  beat-aware recognition remain unchanged. Piano phrasing is a separately
  identified display transformation.

## Verification

`tests/Blaze-Practice-Guide-Tests.cjs` covers input immutability, exact detected
timing, brief-return phrasing, genuine changes, edits, silence/gaps, variable
beats, rate changes, intro/outro seconds fallback, seeks and loop boundaries.
The authenticated Chromium practice test covers visible mode changes,
preparation countdowns, active playback, final rhythm refinement and reduced
motion. These deterministic fixtures verify behavior; listening tests with
the user's actual songs are still needed to assess musical preference.

Research audit: four search queries; primary product documentation and
published research were reviewed. Four primary sources are cited above.
Research routing: general technical/product research.
