# Mac chord recognition performance

Chord preprocessing and neural inference use different execution paths. The
baseline CQT graph mixes FP32 resampling with FP64 spectral arithmetic. Running
it through Core ML adds compilation and partition transfers while much of its
arithmetic still executes on CPU. `ModelBundle` therefore uses the CPU runtime
for this preprocessing graph. BTC, the structured ensemble, and Beat This!
retain their existing Core ML GPU settings on Apple Silicon.

The original weights, FP32 neural inputs, FP64 CQT output, attention context,
overlap, normalization, vocabulary and decoder remain unchanged. Existing
analysis cache identities remain valid.

## Evidence and limits

The native macOS 26 experiment in [run 44133598511](https://github.com/Brooth-C/blaze/actions/runs/44133598511)
compared checksum-pinned production assets with diagnostic profiling enabled.
CQT outputs were byte-identical
between CPU and the original dynamic Core ML path for normal, quiet and silent
inputs at 221184 and 110593 samples. Cold session creation measured about
4.156 seconds through Core ML and 0.0167 seconds on CPU. Warm execution varied
by case; this is an initialization improvement, not a whole-song speed factor
or a physical M3 measurement.

Exact-shape specialization of the structured ensemble was rejected: although
some cases ran faster, quiet and silent output logits differed substantially.
The app keeps its original dynamic ensemble execution.

Local CPU comparisons against released 0.19.6 also preserved complete analysis
JSON, excluding elapsed time, on 30-second constant/transition fixtures and a
150-second transition fixture with silence. This does not establish timing or
provider placement on a user's Mac.

## Regression checks

`tests/Blaze-Mac-Chord-Frontend-Tests.py` checks CPU preprocessing placement while
retaining the neural runtime. With `BLAZE_CHORD_MODEL_DIR` set on an Apple
Silicon Mac, it compares the original Core ML frontend with the app frontend
across 15 normal, quiet, silent, impulse and harmonic cases, including short
and final partial windows. The production Mac workflow runs this checkpoint
comparison after staging assets. The expanded 15-case comparison passed on
macOS 26 in [run 44136094207](https://github.com/Brooth-C/blaze/actions/runs/44136094207).
That repeat measured cold setup at 5.536 seconds through Core ML and 0.0343
seconds on CPU; all CQT comparison outputs were again byte-identical.

`Blaze-Analysis-Lazy-Tests.py`, `Blaze-LV-Projection-Tests.py` and
`Blaze-Sequence-Tests.py` cover numerical parity for feature extraction,
ensemble accumulation, silence decisions and decoder paths.

## Local diagnostics

`BLAZE_ANALYSIS_JOB_TIMING` records input preparation, model verification,
cache lookup, inference, saving and total job time without recording filenames
or paths. `BLAZE_ANALYSIS_TIMING` reports the internal recognition stages.
These are local diagnostic logs, not remote telemetry.

For model-provider profiling on macOS 26 Apple Silicon, use
`tools/benchmark_macos_chords.py` with the production model directory and a
local recording. It preserves results and ONNX profile events in the explicit
output directory. Profiling adds overhead; provider event durations are not
wall-clock durations or a physical GPU-utilization measurement.

## Complete recognition benchmark — November 18

[Native run 44208033216](https://github.com/Brooth-C/blaze/actions/runs/44208033216)
measured the complete app worker on a deterministic 150-second stereo recording.
The timer includes preparation/copying, checksum verification, decoding, all
recognition stages and saving. Each invocation uses new app data to prevent
analysis-cache hits. Model disk caches persist for the warm samples. Profiling
is disabled during timing.

| Complete worker time | Released 0.19.6 | Current development code |
| --- | ---: | ---: |
| First invocation with fresh model cache | 102.46 s | 70.78 s |
| Median of two warm invocations | 59.37 s | 47.68 s |
| Individual warm invocations | 68.72 / 50.03 s | 51.51 / 43.84 s |

These observations correspond to about 31% less first-invocation time and 20%
less warm time. The sample count is small and timings varied substantially;
these figures do not establish an expected improvement on a physical M3.

All 29 chord labels and their boundaries, beat/downbeat maps, tempo, key,
waveform and other result metadata matched across every invocation. Complete
JSON bytes did not match: the unchanged released code itself showed GPU model
score variation of up to 1.75e-6 between processes. The current code varied by
up to 2.81e-6 against the first reference. This score drift is reported
explicitly; it is not labeled byte-identical output or hidden behind a wider
parity tolerance. The CQT-specific 15-case byte-exact check remains separate.

CPU fallback scheduling experiments were rejected. Two threads preserved every
raw neural output in [run 44208971719](https://github.com/Brooth-C/blaze/actions/runs/44208971719)
but increased warm total time to 59.28 s; four threads took 61.02 s and changed
some raw ensemble outputs. The app retains one Core ML fallback thread.

Rhythm recognition is the largest remaining measured stage: its warm median
was 34.55 s out of 47.68 s total. The five-model ensemble took 9.58 s. Future
work should target those stages while retaining their original contexts and
model behavior.

`tools/benchmark_macos_chord_pipeline.py` reproduces whole-worker comparisons;
`tools/verify_macos_chord_threads.py` checks raw neural outputs independently.
The full benchmark workflow is manual so documentation/tooling edits do not
schedule twelve expensive recognitions automatically.

## Chords before rhythm — November 18

Mac Practice now publishes a preliminary guide from the full chord ensemble
before neural rhythm inference starts. It keeps the ensemble predictions and
decoded PCM for the original final beat-aware decoder. No neural model runs
twice and the original model weights, input precision and attention contexts
remain unchanged. Other presentations retain the original stage ordering.

The preliminary guide is explicitly marked while rhythm is pending. Playback,
notation transpose and navigation remain available. Stopping rhythm retains
that preliminary guide for the current process; it does not store an unfinished
result as a completed analysis. Practice settings can still be saved. Once
rhythm finishes, the final guide replaces the preliminary guide without
reloading media or resetting playback. Manual chord edits wait for final
timing because corrections are tied to exact event boundaries.

A local full-model CPU comparison used the existing 150-second fixture:

| Measurement | Time |
| --- | ---: |
| Original pipeline, first available final chords | 19.78 s |
| New pipeline, preliminary full-ensemble chords | 9.56 s |
| New pipeline, final rhythm-aware result | 19.29 s |

All final result fields, including chord scores, labels, boundaries, beats,
downbeats, tempo, key and waveform matched exactly, excluding elapsed time.
This is one Linux CPU comparison, not a native Mac measurement or evidence of
a statistically established reduction in total analysis time. It demonstrates
earlier chord delivery; rhythm computation still takes place afterward.

`Blaze-Chords-First-Tests.py` verifies stage order, final parity, prediction
reuse and cleanup. `Blaze-Chords-First-Jobs-Tests.py` verifies early publication,
source ownership, cancellation/retry and incomplete-cache protection.
`Blaze-Mac-Chords-First-UI-Tests.cjs` uses authenticated loopback serving and
real audio playback to check early chord display, transpose, browsing,
same-ID final refinement and playback continuity during background rhythm.

## Further exact-output decoder experiment — November 18

The observation scorer's indexed projection produces column-major storage,
while Viterbi consumes individual rows. The scorer now packs each completed
128-frame block into row-major storage after all arithmetic. It does not
reorder additions, change precision or retain a full-song emission matrix.

Using saved production predictions for the same 150-second fixture, four
timed samples per variant after warm-up measured the preliminary-plus-final
decoder median at 0.79865 seconds before and 0.76569 seconds afterward
(about 4.1%, or 33 milliseconds). Every candidate sample was faster in this
comparison. This is a small Linux CPU decoder improvement, not a measured
whole-app or physical M3 gain. Raw scores across actual, normal, quiet and
tied FP32/FP64 inputs were exact; the complete recording's preliminary and
final result fields also matched, excluding elapsed time.

Packing before the arithmetic was slower and was rejected. Moving rhythm
spectrogram preparation after chord delivery also preserved output, but an
isolated ABBA comparison did not improve observed chord delivery and increased
total time. That experiment was reverted. Existing model weights, contexts,
precision and the chord-first scheduling remain intact.

The complete-worker benchmark now reports first-chord delivery separately
from final completion so future Mac comparisons measure both user-visible
waiting and total processing.

Candidate selection is also batched over the same 128-frame blocks. The
Viterbi recurrence, beam of 20, silence decisions and tie handling stay
unchanged. Only the selected columns survive each partition; memory remains
bounded independently of recording length. The ordinary row-based decoder
entry point remains available for existing callers and reference comparisons.

A direct combined comparison against the original implementation measured
the preliminary-plus-final decoder median at 0.99090 to 0.84631 seconds
(about 14.6%, or 145 milliseconds), with four warmed ABBA samples per version.
These measurements are from a separate run and are not added to the earlier
percentage. Host variation remains; this is a modest decoder-only Linux CPU
result. All production preview/final frames and input hashes matched.
The whole 150-second recognition was then checked again: every preliminary
and final result field matched the previous pipeline except elapsed time.

`Blaze-Decoder-Layout-Tests.py` checks packed observation scores, bounded
partitions and full sequence paths on FP32/FP64 normal, tied, silent and
near-tied inputs, including small vocabularies and partial blocks. Native
macOS 26 CI runs this alongside the existing recognition checks.
