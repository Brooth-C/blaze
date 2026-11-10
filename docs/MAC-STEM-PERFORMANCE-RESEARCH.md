# Mac stem separation: Logic Pro comparison and Blaze performance audit

Research date: 2026-11-10. Source reviewed: Blaze stable 0.19.0,
main `7b4fd9dab1e1b1ab31a90eb7ca76b2ae98fa9c79` (local tree matches).
Target: physical M3, 8 GB unified memory, macOS 26. Research only; no engine,
model, default, dependency or release changes were made.

## Decision

Blaze enables GPU inference, but its implementation has identifiable overhead.
The first performance experiment should keep the existing piano checkpoint and
measure fewer MLX evaluation boundaries and deferred buffer-cache clearing.
For multi-stem modes, measure model-session creation and graph handoffs before
choosing a native deployment or a different model. GPU utilisation alone is not
the success metric: use file-to-playable-audio time, output quality, memory
pressure and uninterrupted playback.

There is no measured Blaze-versus-Logic comparison on this user's M3. These
findings explain plausible sources of the observed delay; they do not establish
which one dominates, how much faster a change will be, or Apple's internals.

## What Apple's documentation establishes

- Logic runs Stem Splitter locally on Apple silicon. Apple described the initial
  implementation as fast but did not publish an architecture, checkpoint,
  precision, hardware-placement trace or reproducible latency benchmark in the
  reviewed announcements [1]. Guitar and piano were added in 2025 [2].
- The current October 2026 announcement adds separation of drum parts [3]. A
  comparison must record the installed Logic version and selected outputs;
  results from its initial four-stem version are not a current baseline.
- I could not verify a public download of Logic's separation model or an API
  exposing that model. Claims that Logic specifically uses Demucs, Spleeter,
  RoFormer, FP16, or only the Neural Engine are unsupported by these sources.
- Apple's Music Understanding framework returns musical analysis information,
  including key, rhythm, structure and instrument activity. Its documented
  analysis outputs do not provide isolated instrument audio [4]. It is not a
  documented replacement for Stem Splitter.

An integrated model/deployment optimised for Apple's hardware is a reasonable
explanation for Logic's performance, but its precise implementation remains
unknown. A native app wrapper or a Rust rewrite would not automatically fix
Blaze's model scheduling and inference costs.

## Findings in Blaze's actual source

| Finding | Evidence | Consequence and uncertainty |
| --- | --- | --- |
| Piano uses Metal by default | `piano_backend.py`, `mlx_piano_model.py`: Apple Silicon selects MLX, requires Metal and fused attention | This is genuine GPU inference, rather than an ONNX provider merely being registered. It does not measure GPU saturation. |
| Piano evaluates repeatedly and clears its buffer cache inside every transformer | `mlx_piano_model.py:108`: two `mx.eval` calls and one `mx.clear_cache` per transformer, two transformers per block, twelve blocks | 48 inner evaluation calls and 24 cache clears per chunk. These are targets for a controlled experiment; they also bound memory and provide cancellation checkpoints. |
| Extra evaluation calls are not all additional GPU computation | `mlx_piano_model.py:141`: outer evaluation after already-evaluated transformer results | MLX documents that re-evaluating an already materialised array is effectively a no-op [5]. Do not treat every `eval` occurrence as an equal stall or claim that deleting it alone speeds inference. |
| Piano graph is not explicitly compiled | `mlx_piano_model.py`: operations are built through Python helpers and per-band loops; no `mx.compile` | Compilation of a bounded, fixed-shape function is an experiment worth measuring [6], not a guaranteed gain. Compiling the entire graph may increase memory or startup time. |
| Piano retains full FP32 math and substantial context | `mlx_piano_model.py`, `instruments.py`: 38,693,580 stored parameter values, 154,774,320 raw parameter bytes; 20-second chunks | Intermediate tensors and attention dominate more memory than the weight file alone suggests. FP16 could reduce some memory costs, but must preserve quiet details and be benchmarked. |
| Audio is deliberately processed with 50% overlap | `roformer.py:149`: stride is half the chunk length, with boundary padding | Roughly twice the audio context is inferred. This helps seams and quality. Reducing overlap is a quality tradeoff, not an initial no-risk optimisation. |
| Multi-stem ONNX graphs are re-created for every chunk | `roformer.py:52`: read model bytes, checksum, construct session, run, release; `_predict` repeats ten graphs | Repeated disk access, hashing, loading and session initialisation. A compiled disk cache exists, but does not keep inference sessions resident. Exact cost needs phase timing. |
| ONNX graph boundaries use host arrays | `roformer.py`: sequential `session.run` calls return NumPy arrays; `stem_runtime.py` | Boundaries prevent a single persistent device graph. Unified memory avoids a separate VRAM requirement but does not eliminate synchronisation, materialisation or allocation overhead. |
| Five and nine stems are serial pipelines | `roformer.py:218`, `instruments.py:94`: four-stem RoFormer then legacy Spleeter piano, followed by an instrument-refinement pass for nine stems | These modes perform more work than standalone MLX piano isolation. Improving MLX piano alone does not fix five- or nine-stem performance or their piano estimator. |
| Core ML excludes the Neural Engine | `stem_runtime.py:71`: `MLComputeUnits=CPUAndGPU` | `ALL` would permit the Neural Engine [7,8], but does not guarantee placement, compatibility or faster execution. MLX's Metal backend is separate from this setting. |
| Surrounding DSP uses CPU | `roformer_transform.py`, `native_piano.py`: NumPy spectral transforms, complex masking and overlap-add; FFmpeg decode | Measure their contribution. Moving every operation to the GPU can add overhead for small tasks [9]. |

### Concrete work-count example, not a timing result

For a 180-second stereo recording at 44.1 kHz, applying the source's actual
chunk/stride/padding schedule gives:

| Stage | Chunks | Context evaluated | ONNX session constructions |
| --- | --- | --- | --- |
| Standalone MLX piano | 20 x 20 seconds | 400 seconds, including overlap/padding | 0 |
| Four-stem RoFormer stage | 35 x 11 seconds | 385 seconds, including overlap/padding | 350 |

The MLX piano case also invokes 480 inner-loop cache clears. The four-stem row
excludes subsequent piano/instrument passes. These counts were calculated from
the current constants and loop, not extrapolated from a machine benchmark.

## What measurements we already have, and their limits

`MAC-NATIVE-PIANO.md` retains an earlier hosted virtual M1/7-GiB comparison:
native ONNX piano took 144.8 seconds on CPU, 550.5 seconds with a fresh Core ML
cache and 879.9 seconds on its second Core ML run. Core ML's process high-water
mark was 5.92 GB and swap was used; inspected compute plans placed operations
on CPU. The input was a one-second tone padded to a twenty-second context.

That receipt demonstrates that enabling a provider is insufficient evidence of
GPU speed. It does **not** describe the released MLX piano path on a physical
M3 and cannot establish a speed ratio against Logic. Hosted jobs without a
Metal device skip actual GPU timing; their successful status is not a GPU
benchmark. No new hardware benchmark was run for this research.

## Alternatives worth comparing

1. **Optimise the current MLX piano path first.** Preserve the checkpoint,
   context, overlap, output gain and FP32 baseline. Test deferred cache clearing
   with the existing cache limit, then bounded compilation/evaluation changes
   independently. Keep cancellation responsive and retain cleanup on failure.
2. **Native MLX multi-stem deployment.** `ssmall256/mlx-audio-separator` offers
   reference implementations with GPU spectral transforms and deferred cache
   clearing. Its authors report 1.40–2.50x speedups over their upstream baseline
   on an M4 mini for four tested models [10]. Those are not Blaze comparisons,
   M3 measurements, or evidence that every supported model is faster. Its
   six-stem BS-RoFormer-SW model card lists the weight licence as unknown [11];
   do not adopt those weights for commercial distribution without resolving it.
3. **Native Core ML SCNet for four standard stems.** `demixr/scnet-executorch`
   reports preserving native LSTM operators rather than decomposing them,
   with a 0.36-second warm chunk on the author's development Mac [12]. This is
   useful deployment evidence, not an M3 speed promise, a full-song benchmark,
   or a piano solution. Verify checkpoint licensing and quality independently.

Do not install or replace the inference stack merely to reproduce external
headline timings. A six-output model could reduce serial passes, but comparable
piano quality, memory usage and distribution rights remain selection criteria.

## Implementation-ready measurement sequence

1. **Establish an apples-to-apples baseline.** Same physical M3/8-GB Mac, OS,
   AC-power/energy settings and source WAV; record Logic version, region length,
   enabled stems, first-run and repeated timings. Compare piano to piano and
   full-song separation to full-song separation. Record output readiness rather
   than the time a progress window closes.
2. **Measure Blaze by phase.** Model validation/loading, session creation,
   decode, spectral transform, inference, reconstruction and file writing.
   Use the existing `tools/benchmark_macos_stems.py` for standalone piano CPU,
   Core ML and MLX reports; it currently does not benchmark five/nine stems or
   Neural Engine placement. Extend only for the experiment being performed.
3. **Capture hardware evidence.** Instruments Metal System Trace for idle gaps,
   GPU work and CPU waits; Core ML compute plans for ONNX placement; memory
   pressure and swap before/during/after. Record model-allocated memory and
   total process memory separately. GPU History alone cannot identify the cause.
4. **Change one bottleneck at a time.** First piano cache/evaluation cadence;
   next bounded compilation or DSP; for ONNX, a small bounded session cache or
   native fused deployment. Do not retain every graph and arena blindly on an
   8-GB shared-memory machine. Compare `CPUAndGPU` and `ALL` only after measuring
   compatibility and dispatch; retain the fastest verified path for that model.
5. **Accept improvements using both speed and behaviour.** Compare cold/warm
   file-to-WAV latency over repeated runs, numeric output differences and
   listening samples (acoustic piano, dense mixes, quiet passages, reverb,
   sustained synths and chunk seams). Confirm duration/gain, reconstruction,
   cancellation, continued playback and concurrent chord analysis. No speedup
   percentage should be promised before this physical-device comparison.

The immediate recommendation is to remove avoidable runtime overhead while
keeping the current piano quality. Consider a different model only after that
baseline shows whether model computation itself remains the limiting cost.

## Sources and research limits

Primary platform documentation establishes supported behaviour, not independent
performance comparisons. Repository timings below are author-reported and
specific to their hardware and baselines.

1. Apple, [Logic Pro takes music-making to the next level](https://www.apple.com/newsroom/2024/05/logic-pro-takes-music-making-to-the-next-level-with-new-ai-features/), 2024-05-07.
2. Apple, [Logic Pro amplifies beat making](https://www.apple.com/newsroom/2025/05/logic-pro-amplifies-beat-making-on-mac-and-ipad-with-advanced-new-capabilities/), 2025-05-28.
3. Apple, [Apple Creator Studio updates](https://www.apple.com/newsroom/2026/10/apple-creator-studio-adds-powerful-new-ai-features-and-even-more-creative-tools/), 2026-10-27.
4. Apple Developer, [Meet the Music Understanding framework](https://developer.apple.com/videos/play/wwdc2026/253/), WWDC26; analysis capabilities, not a separation model API.
5. MLX, [Lazy Evaluation](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html), evaluation overhead and repeated-evaluation semantics.
6. MLX, [Compilation](https://ml-explore.github.io/mlx/build/html/usage/compile.html), function compilation and startup considerations.
7. ONNX Runtime, [Core ML Execution Provider](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html), compute units, shape handling and compute-plan profiling.
8. Apple Developer, [MLComputeUnits](https://developer.apple.com/documentation/coreml/mlcomputeunits), permitting automatic hardware selection.
9. MLX, [Unified Memory](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html), shared arrays and operations better suited to CPU.
10. [ssmall256/mlx-audio-separator](https://github.com/ssmall256/mlx-audio-separator), Performance Snapshot and Stable Runtime Tuning; author-reported, not independently reproduced.
11. [BS-RoFormer-SW packaging/model card](https://huggingface.co/ssmall256/mlx-audio-separator/blob/main/cards/bs-roformer-sw.md), weight-licence status.
12. [demixr/scnet-executorch](https://github.com/demixr/scnet-executorch), native Core ML LSTM deployment and author-reported chunk timings.

Web search and page extraction were used. The installed Obscura browser was
attempted, including outside the sandbox, but its SSRF protection rejected this
environment's private proxy address; those attempts yielded no page evidence.
The web tool supplied the cited pages instead. No live Logic session or physical
M3 was connected, and no external package/model was installed for this report.
