# Rhythm engines and application workflows

Research date: November 18, 2026. Scope: offline, commercially distributable
Blaze on Apple Silicon, with macOS 26 remaining the supported build target.
This document records research and proposed experiments; it does not change
the recognition pipeline or select a replacement model.

## Decision

No reviewed source establishes an engine that is both faster on an M3 with
8 GB and equally accurate to Blaze's existing full Beat This! model. The first
experiment should preserve that model and investigate its native execution
path. Smaller models and different trackers are separate accuracy experiments.

For responsiveness, consider separating preliminary chord display from final
rhythm-aware decoding. Background processing changes when results appear;
it does not remove the rhythm computation or guarantee less total work.

## What is actually slow in Blaze

The [complete-worker benchmark](MAC-CHORD-PERFORMANCE.md) measured a synthetic
150-second stereo fixture on native macOS 26 CI. Current warm total time was
47.68 seconds, with a 34.55-second rhythm-stage median. This identifies rhythm
as the largest measured target. It is not a physical M3/8 GB measurement, a
natural-song accuracy evaluation, or a guaranteed runtime for the user's music.

The existing implementation:

- Uses Beat This! `final0`, its original FP32 weights and input precision.
- Retains 30-second/1500-frame context, original borders, overlap and tail work.
- Uses Core ML GPU settings through ONNX Runtime, with unsupported operations
  eligible for CPU execution. Selecting that provider does not prove that all
  work runs on the GPU or reveal its physical utilization.
- Completes rhythm before structured ensemble inference and final decoding.
  The decoder receives beat positions; removing them can change chord labels
  and boundaries, not just hide BPM and bar lines.
- Already caches complete analyses by audio content and recognition identity.
  Caching is therefore not a new explanation for faster first-time analysis.

Relevant implementation: `music_studio/engine.py`, `rhythm.py`, `server.py`,
`store.py`, and `stem_runtime.py`. The current cache identity includes source,
baseline/frontend model hashes and engine version. A future independently
replaceable rhythm backend needs its own explicit model/configuration identity;
otherwise a changed rhythm model could reuse an incompatible saved analysis.

## What other applications document

| Application | Documented behavior | Lesson and limit |
| --- | --- | --- |
| Logic Pro | Smart Tempo supports Keep, Adapt and Automatic behavior; beat/downbeat and time-signature hints refine analysis. For multitrack material it analyzes a selected downmix and shares the tempo map. | Analyze the appropriate source once and allow correction. The reviewed documentation does not publish Smart Tempo's model architecture, weights, GPU placement or M3 throughput. |
| Ableton Live 12 | Saves analysis in `.asd` files and reuses it; caches decoded compressed audio. Automatic analysis of long samples can be disabled. | Avoid repeated decoding and analysis. Its manual explicitly acknowledges that long first-time sample analysis can prevent that sample playing until completion. |
| rekordbox 7.2.14 | Users can select BPM/Grid, key, phrase and vocal analysis. High-precision BeatGrid is slower and more accurate. Cloud Analysis can retrieve previously computed annotations. | Select only needed work. Normal/high-precision modes are an accuracy tradeoff; cloud lookup is not accelerated first-time offline inference. |
| Moises | Consumer-service support documentation requires an internet connection. | Its experience does not establish equivalent local Mac throughput. |
| Music.AI | Offers hosted BPM/beat analysis and, separately, a commercial Embedded SDK. Its software page advertises local beat detection without servers. | On-device commercial licensing is a legitimate option. Reviewed public pages do not establish SDK price, Mac deployment requirements, M3 timing or comparative rhythm accuracy. |

Sources: [Logic Smart Tempo](https://support.apple.com/en-in/102165),
[Logic multitrack analysis](https://support.apple.com/guide/logicpro/lgcpc87041da/mac),
[Ableton analysis files and decoding cache](https://www.ableton.com/en/manual/managing-files-and-sets/#analysis-files-asd),
[rekordbox manual](https://cdn.rekordbox.com/files/20260409151936/rekordbox7.214_manual_EN.pdf),
[rekordbox Cloud Analysis](https://rekordbox.com/en/support/faq/rekordbox7/#faq-50887),
[Moises offline requirements](https://help.moises.ai/hc/en-us/articles/9173509988124-Is-it-possible-to-use-Moises-offline),
[Music.AI beat module](https://music.ai/modules/transcription/beats/),
[Music.AI local software](https://music.ai/solutions/software/),
[Embedded SDK](https://music.ai/embedded-ai/).

The user's name “mussia ai” was not unambiguously identified. Moises and
Music.AI were researched without assuming either is the intended service.

## Apple's public native alternative

Apple's Music Understanding framework provides on-device, offline music
analysis. Rhythm results include beat positions, bar boundaries and BPM.
Sessions accept an AVAsset or PCM-buffer sequence, support cancellation, and
can request particular analysis types rather than every available analysis.

Official availability metadata requires **macOS 27.0 or later**. This is not
a drop-in backend for Blaze's macOS 26 release. It could be an optional future
backend, requiring separate supported-platform and accuracy decisions.

Apple explicitly identifies Final Cut Pro as a user of this technology. That
does not establish that Logic Pro Smart Tempo uses the same engine. Public
documentation also does not establish M3 speed relative to Beat This! or
incremental delivery of rhythm results; loudness is the explicit incremental
example.

Sources: [framework and availability](https://developer.apple.com/documentation/musicunderstanding.md),
[WWDC26 presentation](https://developer.apple.com/videos/play/wwdc2026/253/).

## Practical engines

| Engine | Evidence | Decision for Blaze |
| --- | --- | --- |
| Beat This! `final0` | Existing model; approximately 20 M parameters, 78 MB checkpoint. MIT code and weights. Predicts beats/downbeats without requiring DBN postprocessing. | Preserve as reference. Investigate runtime overhead before changing musical behavior. |
| Beat This! `small0` | Approximately 2 M parameters, 8.1 MB checkpoint. Paper's GTZAN mean beat F1 changes 89.1 to 88.8; downbeat F1 78.3 to 77.2. | Best straightforward smaller-model experiment. Smaller checkpoint size is not a measured speed factor, and accuracy is not unchanged. |
| Original BeatNet | Public CRNN/particle-filter implementation, checkpoints, CC-BY-4.0 repository; online and offline modes. | Useful compact streaming candidate. Stock CPU/CUDA support does not provide an Apple GPU backend or equal-accuracy proof. Audit bundled model/dependency terms when selecting a complete deployment. |
| BeatNet+ C++/ggml port | Author reports a 170-second EDM track in about 6.5 seconds on M1 Max. Native CPU/Metal paths; stochastic decoding and GPU numerical differences can change beats. | Useful engineering evidence, not an M3 result or cross-model accuracy comparison. Converted pretrained weights are explicitly non-commercial; exclude from a commercial default without authorization. |
| BEAST | Public streaming Transformer implementation and checkpoint; paper reports algorithmic latency below 50 ms. | Consider for live following. Algorithmic latency is not the time required to analyze a complete file, and does not establish offline accuracy equivalence. |
| Explore This! | New 2026 learned-tatum-grid tracker, MIT code and weights, public checkpoints. Improves some continuity metrics but not all F1 metrics. | Research candidate; no demonstrated M3 speed/quality win over the current model. |

Sources: [Beat This! models and license](https://github.com/CPJKU/beat_this),
[Beat This! paper, Table 2](https://arxiv.org/html/2407.21658v1),
[BeatNet](https://github.com/mjhydri/BeatNet),
[BeatNet+ port, performance and licensing](https://github.com/key2/beatnetplus.cpp),
[BEAST implementation](https://github.com/WildHoneyPie/BEAST),
[BEAST paper](https://arxiv.org/abs/2312.17156),
[Explore This!](https://github.com/CPJKU/explore_this),
[Explore This! paper](https://arxiv.org/html/2610.14817v1).

BeatMamba and Beat-Aware Transformer are relevant ICASSP 2026 efficiency
research. Reviewed searches did not locate a sufficiently documented public
implementation/checkpoint/license and Mac benchmark for direct adoption.
They remain watchlist items, not ready replacement dependencies:
[BeatMamba](https://ieeexplore.ieee.org/abstract/document/11464751),
[Beat-Aware Transformer](https://ieeexplore.ieee.org/abstract/document/11461306).

## Lighter DSP and licensing distinctions

Essentia's RhythmExtractor2013 offers multifeature and Degara methods for tempo
and beat positions. librosa provides dynamic-programming beat tracking and
local-pulse estimation; aubio provides native C tempo/onset analysis. These
are plausible quick-preview engines, not proven replacements for the same
neural downbeat/meter behavior on piano, rubato and mixed genres.

Essentia uses AGPL/commercial licensing and its pretrained models have
separate non-commercial/commercial terms. Aubio is GPL-3.0-or-later. Madmom's
BSD source-code license must not be confused with its generally
CC-BY-NC-SA-4.0 model/data license. These distinctions matter for the actual
Blaze distribution; permissive wrapper code does not relicense model weights.

Sources: [Essentia rhythm engine](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html),
[Essentia licensing](https://essentia.upf.edu/licensing_information.html),
[librosa beat tracking](https://librosa.org/doc/main/api/generated/librosa.beat.beat_track.html),
[aubio](https://github.com/aubio/aubio),
[madmom licenses](https://github.com/CPJKU/madmom#license).

## Native implementation reference

[Palmier's Beat This! Core ML conversion](https://github.com/palmier-io/palmier-pro/blob/main/models/beat_this/README.md)
demonstrates a direct graph with the log-mel frontend included and unsupported
tensor operations rewritten. Its packaged model uses `small0` and FP16.
Published parity gates cover a click fixture with one-frame tolerance.

This is a useful conversion reference, not a validated replacement for Blaze's
`final0` FP32 pipeline. A Blaze experiment must preserve the full model,
precision request, normalization, context, tail and stitching rules, then
compare raw predictions and musical results. Same weights alone do not prove
equal results after graph conversion. Profile CPU/GPU placement and transfers
before attributing the existing 34.55 seconds to a specific runtime defect.

## Proposed implementation order

1. Benchmark existing `final0` through direct Core ML, and consider MLX only
   if profiling supports that route. Retain the original runtime as reference.
2. Separately experiment with chord-first display: compute ensemble outputs,
   show explicitly preliminary chords, retain those outputs, then rerun only
   final decoding after the original rhythm completes. Preserve corrections
   and selection during the update. Final musical parity must be tested.
3. Add an independently versioned rhythm cache if rhythm becomes a separate
   job. Reuse complete analyses already cached today. Chord display transpose
   and playback must not invalidate unchanged source-audio rhythm analysis.
4. Benchmark `small0` and original BeatNet as optional alternative engines.
   Do not label either an unchanged-quality optimization in advance.
5. Evaluate Apple's framework only in a separately authorized macOS 27 path.
   Keep macOS 26 support and the existing release target unchanged.

On an 8 GB Mac, running every model and stem separator concurrently can raise
memory pressure and GPU contention. Background work needs scheduling and
cancellation, not merely more simultaneous GPU jobs. GPU dispatch is useful
where it reduces measured wall time; tiny DSP/streaming operations may be
faster on CPU. The BeatNet+ port is one published example of this distinction.

## Acceptance evidence before selecting an engine

Measure first-use and warm full-worker time, time to preliminary chords,
time to final chords/beats, peak memory and playback responsiveness. Test on
the user's physical M3/8 GB as well as native macOS 26 CI; record whether
separation is running. Separate algorithm lookahead from file throughput.

For an execution-only port, compare raw beat/downbeat predictions, all chord
labels and boundaries, BPM and bars against the current model, including
silence, quiet audio, partial tails and long recordings. Report GPU numerical
variation explicitly rather than increasing a tolerance to hide regressions.

For a different model, evaluate annotated held-out material with beat and
downbeat F1, continuity, half/double-tempo errors and downstream chord timing.
Include piano/rubato, acoustic and percussion-heavy music, odd/changing meters,
intros and ambiguous passages. Use evaluation splits permitted by each
model's training history. Compare complete pipeline costs, including any
required stem separation, resampling or postprocessor.
