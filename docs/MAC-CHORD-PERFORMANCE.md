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
compared checksum-pinned production assets. CQT outputs were byte-identical
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
comparison after staging assets.

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
