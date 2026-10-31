# Native piano isolation and bounded Mac runtime

The standalone **Isolate piano** action now uses Mega53's original acoustic-piano
head (index33) instead of the Spleeter estimate. It retains the full modeled
frequency band and applies the original complex mask, preserving phase. The
second WAV is input minus piano; outputs retain source duration, stereo layout
and relative gain. It does not synthesize an instrument or merge digital piano,
keys and synth estimates into the piano track.

This is a candidate implementation for the M3/8 GB quality complaint. It has
not been auditioned against the user's original/output pair. No cleaner-sound,
faster-than-Spleeter or M3/8 GB performance claim is established by conversion
tests. Five-/nine-stem model selections remain unchanged pending that evaluation.

## Model and packaging

Original checkpoint and permission are pinned by `instrument_assets.py`:
`mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`, SHA256
`c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f`.
The [creator's exact-weight MIT grant](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245#issuecomment-5834608838)
permits conversion and commercial redistribution. Retain its notices and the
training-data limitation. No noncommercial or unverified six-stem weights are
added.

Only the new independent head is added to the bundle: **49,684,302 bytes**,
SHA256 `13a02c35968a6d8cd56ea4384f706b976cfa3d952b5e48ef3d502e6061ae1697`.
It shares the existing pinned front end and twelve transformer blocks. The
app does not load all 53 heads or include the 1.37 GB training checkpoint.
Fourteen graph stages execute sequentially, releasing their sessions rather
than retaining all runtime arenas. The normal 20-second context and 50% overlap
are preserved. The existing bounded streaming/cancellation/output cleanup and
background-job ownership contracts remain in use.

`tools/instruments/export_piano.py` verifies the original source revision,
checkpoint, config and head order, strictly loads the selected parameters, and
exports the native head. Its reference is evaluated before export surgery.
`verify_piano.py` checks the reviewed export pin and original-computation parity.
On deterministic latent input, both ORT1.20.1 and ORT1.31.0 produced maximum
absolute error **9.54e-7**, RMS approximately **5.27e-8**, and 99.9th percentile
error **2.98e-7**. This checks head conversion, not musical quality. Shared trunk
conversion uses the same previously pinned graphs.

The shared nineteen-graph instrument export also passed its original-reference
check under ORT1.31: RMS **9.63e-9**, 99.9th percentile **8.20e-8**, maximum
**9.54e-7**. Linux conversion/runtime-check peak RSS was about **2.80 GiB**.
This is not a Mac memory benchmark. Real native-piano inference produced finite
stereo WAVs with exact duration and additive reconstruction. A second export to
a different directory reproduced the pinned piano-head hash. Tests additionally
cover cancellation arriving during session creation, releasing the session and
profile before returning cancellation.
The packaged UI receipt identifies the actual native piano checkpoint/head and
is checked against its pins. Its finite smoke-test budget accounts for both
real nine-stem and new native-piano jobs; it is not a responsiveness benchmark.

The Mac CI workflow builds this artifact in a separate Linux **conversion** job
and downloads it into the model cache before Mac packaging. This is not a
Linux Mac-app build or native Mac validation. No unpublished release URL or
runtime model downloader is used. The stage and bundle builders require the
exact head manifest, size and checksum; a missing model fails explicitly rather
than silently running the old estimate. The app bundles license notices beside
the model. Mac application build/validation remains on macOS26 arm64. Existing
macOS15/Intel installer checks are retained; other platforms are unchanged.

For a local build, use the pinned CPU conversion dependencies listed in the CI
job, then:

```sh
python tools/instruments/export_piano.py --msst <pinned-msst-checkout> \
  --checkpoint <verified-mega53.ckpt> --output build/native-piano
python tools/instruments/verify_piano.py --assets build/native-piano
mkdir -p build/mac-assets/stem-models/native-piano
cp build/native-piano/head-piano.onnx build/mac-assets/stem-models/native-piano/
python tools/stage_macos_studio.py --work build/mac-assets --arch arm64
```

The complete Mac stager still supplies the existing chord, stem, decoder and
downloader dependencies. This does not replace the existing packaging workflow.

## Core ML evaluation

CPU remains the default. `BLAZE_STEM_BACKEND=coreml` is an explicit experimental
path for RoFormer-based separation on Apple Silicon. It requires ORT1.31+, an
included CoreML provider and successful provider registration. The Mac workflow
now pins ORT1.31.0; other-platform requirements and the conversion environment
are unchanged. ORT1.20.1 silently ignored the modern cache/options keys, which
is why simply adding provider strings to the old dependency was insufficient.

The candidate uses MLProgram, CPUAndGPU, static shapes and eligible subgraph
delegation. On these exports, Loop control remains on CPU; static-shape or
unsupported operations can prevent further delegation. Python's automatic
whole-session failure retry is disabled for this explicit evaluation, while
normal graph partitioning to CPU is permitted. Provider registration alone is
not reported as GPU execution.

Compiled disk caches are isolated by model bytes, ORT version and effective
runtime settings. Verified ONNX bytes are passed in memory; no model paths can
redirect external ONNX data. Sessions are released after each graph. The cache
does not retain fourteen resident sessions or unbounded GPU tensor arenas.
Cache directories live under `~/Library/Caches/Blaze/StemCoreML`; they are
rebuildable disk caches and can be removed while the app is closed.

Core ML compilation itself cannot be interrupted by ORT's inference RunOptions;
an initial compilation may delay cancellation. Inference uses the existing
interruptible runner. This is another reason the experimental backend is not
the default until native responsiveness and cancellation are measured.

## Measure on the user's Mac

Use the same authorized recording and staged model directory for all runs on
**M3 / 8 GB / macOS26**. The benchmark command rejects other platforms/OS
versions. Each output directory must be new; it includes WAVs and a report.

```sh
python tools/benchmark_macos_stems.py --source <recording> --models <stem_models> \
  --output build/piano-legacy --mode piano-legacy --backend cpu
python tools/benchmark_macos_stems.py --source <recording> --models <stem_models> \
  --output build/piano-native-cpu --mode piano --backend cpu
python tools/benchmark_macos_stems.py --source <recording> --models <stem_models> \
  --output build/piano-native-coreml --mode piano --backend coreml \
  --reference build/piano-native-cpu/benchmark.json
```

Reports include chip/OS/RAM, source hash, audio duration, complete decode-to-WAV
time, time/audio ratio, cumulative process high-water RSS, swap snapshots and
per-graph session creation records. Initial Core ML compilation uses a new
private cache; the next run reuses it. RSS is process-lifetime high-water, not
an isolated peak for each run. Compare whole-app memory pressure and playback/
chord-analysis behavior separately before enabling a default backend.

ORT profiles aggregate CPU and CoreML node events, including eligible loop-body
events. No CoreML events makes the requested GPU evaluation fail explicitly.
Kernel-event durations are sums and must not be presented as wall time.
CoreML events prove delegation, not actual Metal GPU utilization; native
Instruments and compute-plan evidence are still needed for that assertion.

PR/manual Mac CI additionally profiles CPU and cold/warm CoreML runs against
the same checksum-pinned assets and decoder used by packaging on macOS26. This
independent model check runs alongside the full app build, which separately
verifies those assets inside the real package. Its deterministic tone checks
runtime execution, not piano separation quality. It reports the runner's chip
and RAM; those timings must not be attributed to the user's M3/8 GB. Profile
artifacts are retained even if acceleration initialization or delegation fails.
Candidate WAVs are compared with the matching CPU run in bounded blocks. The
diagnostic gate allows at most 1% normalized RMS error (or absolute RMS below
1e-5 for near-silent estimates) and 0.01 maximum absolute sample error. These
are explicit evaluation tolerances, not an audibility guarantee. A format,
duration, finite-sample or tolerance failure retains the report and fails the
profile check rather than reporting successful acceleration.

Listen to volume-matched original/piano/accompaniment for attacks, sustain,
reverb, pad bleed and false piano on recordings without piano. Include acoustic
and electric piano as distinct cases. Do not enable the candidate by default
in a stable release solely from numeric conversion tests, generic benchmarks,
or another machine's timings. Preserve the known release until native package
and user-recording comparisons support replacing it.
