# Piano quality and faster stems on M3 / 8 GB

Research date: 2026-10-31. Scope: local Mac separation, Apple Silicon,
commercially usable model weights. User reports a pad-like result specifically
from **Piano isolation**, on an **M3 with 8 GB unified memory**. No source/output
audio pair was supplied, so the reported artifact has not been auditioned or
diagnosed conclusively. This pass changes documentation only.

## Decision

No retrieved evidence establishes a replacement that is simultaneously cleaner
than Blaze's piano output, faster on M3/8 GB, and cleared for commercial
redistribution. Do not represent an architecture name or a faster high-end Mac
benchmark as that evidence.

- **Strongest piano-quality lead in the retrieved published comparison:**
  BS-RoFormer SW six-stem. Evaluate a Core ML CPU+GPU version if the exact
  weights receive appropriate commercial permission. Current provenance and
  redistribution permission remain unresolved.
- **Most interesting lightweight piano specialist:** tjpurdy's Piano Separation
  Model small. Its author marks the weights noncommercial. A separate license
  and actual M3 benchmark would be needed before making it Blaze's default.
- **Best permission-supported quality experiment using Blaze's existing model
  lineage:** export Mega53's native piano head and compare it with Spleeter.
  Quality, runtime and 8 GB suitability are unproven; do not promise a speedup.
- **Performance work with the broadest applicability:** profile a bounded GPU
  runtime, MLX or cached Core ML, on the chosen checkpoint. Accelerating
  Spleeter preserves its source-classification limitations.

Keep the product simple: one piano action that returns piano plus accompaniment,
one normal stem mode, and optional extended instrument separation. Avoid a
default ensemble on an 8 GB device. These are recommendations, not implemented
changes or claims about a new release.

## What the current code actually does

| Action | Current path | Consequence |
| --- | --- | --- |
| Piano isolation | `PianoSeparator`, Spleeter five-stem spectral U-Nets; all five logits are jointly normalized before selecting piano | The fast action still runs five graphs. It is not a newly trained piano specialist. |
| Four stems | SCNet | Native drums, bass, other and vocals; no native piano output. |
| Five stems | BS-RoFormer ep17 four-stem output, followed by Spleeter on Other | Two sequential stages; piano retains Spleeter's limitations. |
| Nine stems | The five-stem path, followed by selected Mega53 heads on remaining Other | Three sequential stages; more output labels do not establish higher quality. |

Source audit: `music_studio/piano.py`, `stems.py`, `roformer.py`,
`instruments.py`, `instrument_assets.py` and `stem_jobs.py` at commit
`ed62a7d`. All current model paths explicitly request
`CPUExecutionProvider`; there is no inference selection for Metal, MLX or
Core ML in these classes. SCNet keeps a session; piano and RoFormer create and
release individual graph sessions repeatedly to bound memory. The latter also
read and hash graph bytes on each invocation. The main RoFormer evaluates ten
graphs per chunk; the existing extended instrument pass evaluates nineteen.
Those are parts of models, not ten or nineteen independent model ensembles.

The separation worker already runs in the background with utility quality of
service on Darwin. Being asynchronous does not remove its CPU/memory cost.
Any new runtime must preserve browsing/playback, chord analysis, cancellation
and source ownership rather than blocking the UI or starting unlimited jobs.

## Why the piano can sound like a pad

Verified implementation limits:

1. The piano action uses the older Spleeter five-stem model. The output is an
   estimate of piano-like content, not confirmation that a piano was present.
   Other keyboards or sustained material can leak into it.
2. Blaze uses FFT4096, hop1024 and 1024 modeled frequency bins at 44.1 kHz.
   The modeled band ends at approximately **11.0 kHz**; higher bins in the
   piano output are zero. Spleeter's own FAQ confirms this limitation of its
   base models. This removes high-frequency detail, but does not alone prove
   the cause of the user's pad-like result.
3. The estimate applies magnitude masks to the original complex spectrum. It
   does not synthesize a replacement piano or run a pad instrument. A weak
   attack estimate, sustained bleed or model confusion could make the result
   sound pad-like. Which occurred requires the actual audio pair.
4. Existing conversion tests check masks, transforms, duration, reconstruction
   and cancellation. They do not demonstrate natural piano timbre on real
   mixed recordings. The piano mask index is consistent with the named export
   order and the retained conversion reference; no simple swapped-stem label
   was identified in the inspected path.

Do not repair this complaint by generating MIDI and resynthesizing piano,
adding reverb, or renaming a keys estimate. The requested feature isolates the
existing instrument. Do not automatically filter out pads with an unvalidated
EQ rule that also removes piano sustain.

Spleeter documents alternate 16 kHz configurations but warns that its weights
were trained below 11 kHz and extrapolation can cause artifacts. Blaze's pinned
exports have a fixed 1024-bin interface: changing one constant is not a safe
upgrade. A wider-band export would need conversion and listening validation,
and would not establish better piano discrimination.

## Candidate comparison

| Candidate | Piano / stem evidence | Speed and memory evidence | Commercial readiness |
| --- | --- | --- | --- |
| BS-RoFormer SW six-stem | Native vocals, drums, bass, guitar, piano and Other. MVSEP reports piano SDR **7.83**, versus **5.89** for its SCNet Large piano specialist and **2.23** for Demucs six-stem in its piano comparison. | A separate Core ML port reports a 3:44 song taking **22:41 CPU → 2:56 CPU+GPU**, on an unspecified M-series **16 GB MacBook Air**. No verified M3/8 GB timing or memory result. | Weight provenance/license unresolved. MIT driver code and a mirror's MIT tag do not establish commercial rights to the underlying weights. |
| Mega53 native piano head | Original configuration distinguishes piano, digital-piano, keys, organ and synth. Blaze currently exports guitar/string/brass/synth heads, not native piano. No retrieved piano-specific result establishes superiority to Spleeter. | A piano-only export could omit unused heads, but still runs the shared twelve-block trunk. Existing nineteen-graph family export measured about 2.62 GiB peak process RSS on Linux; that is neither this proposed export nor a Mac memory guarantee. | Creator explicitly grants MIT rights to the exact 53-stem weights, including commercial integration/conversion/redistribution. Retain attribution/notices; the grant is not an independent clearance of all training audio. |
| tjpurdy Piano Separation Model small | Acoustic-piano specialist; author says electric-piano variants are unsupported. Approximately **17 MB**. | Author claims about 1 second per minute of audio on a Colab T4 with 3 GB VRAM. This is not an M3 or end-to-end Mac benchmark. | **CC BY-NC 4.0**; cannot become the commercial default under that license. |
| SCNet / SCNet Large piano specialist | MVSEP's piano specialist reports 5.89 SDR. The public four-stem SCNet and SCNet XL checkpoints do not supply piano separately. | General SCNet architecture efficiency results do not establish the piano specialist's runtime or M3 behavior. | No public, commercially cleared exact piano-specialist checkpoint was verified. SCNet XL IHF's exact-weight permission inquiry remains unanswered in the inspected issue. |
| Demucs six-stem / MLX Demucs | Native guitar and piano, but original authors explicitly warn that piano has substantial bleed/artifacts and is not working well. | MLX demonstrates fast inference on high-end Apple hardware; those figures are not applicable to M3/8 GB. | Original-author weight rights remain unclear/scientific-use restricted; permissive conversion-code labels do not resolve them. Poor piano evidence also makes this a weak quality choice. |
| Banquet / query-bandit | Audio-query-conditioned extraction; paper reports improved piano/guitar results over HTDemucs6 on MoisesDB. Requires a reference query rather than the current simple fixed-stem action. | No retrieved M3/8 GB evidence. Query encoder and inference memory must also be counted. | Author-linked checkpoint record is **CC BY-NC-SA 4.0**, despite MIT code. |
| SAM Audio | Promptable target/residual separation, rather than a verified one-pass fixed multi-stem replacement. | Official example recommends CUDA; span prediction and reranking increase latency/memory. No verified suitability as a fast M3/8 GB piano default. | Gated weights and custom license; assess separately. Not an immediate lightweight replacement. |

The SDR figures above are **operator-reported**, not independent Blaze tests.
The cited piano table does not include Blaze's Spleeter implementation. Do not
compare a four-stem MUSDB average directly with a piano-only score or claim an
improvement over Spleeter without a shared test set.

## Mac acceleration: what is supported versus measured

### MLX

`ssmall256/mlx-audio-separator` supports several separation architectures,
including BS/Mel RoFormer. Its release snapshot reports **2.16×** speedup over
`audio-separator` for the vocal `ep317` RoFormer on an **M4 mini**, using a
12-song MUSDB18-HQ subset. That is a different model from Blaze's four-stem
`ep17`, not a piano benchmark, and not an M3 estimate. Runtime code licensing
does not grant rights to every supported checkpoint. Exact architectures,
selected-head exports, transforms and parity still need verification.

### Core ML

Official ONNX Runtime documentation describes the CoreML provider, MLProgram,
compute-unit selection, static-shape requirements and a persistent model
cache. Unsupported operations can fall back to CPU. A provider being selected
does not prove that the entire graph runs on the GPU or Neural Engine.
Compilation can be expensive; cache identity must change when model content
changes. Do not recreate and compile an uncached model for every chunk.

The six-stem port is useful evidence for GPU acceleration, but reports crashes
with CPU-only/CPU+Neural Engine configurations for that model. Its tested
`CPUAndGPU` route is the relevant experimental lead. It reports **0.39% NRMSE**
versus its FP32 baseline; its separate wording about bit-identical outputs
must not be repeated as numerical equivalence. No evidence makes its 16 GB
result an 8 GB guarantee.

For M3/8 GB, first evaluate batch one, a bounded cache, one separation job and
appropriate memory headroom for macOS, Blaze playback and chord analysis.
Keeping every graph/session resident may reduce loading time while worsening
memory pressure. FP16 is an evaluation option, not an automatic quality-neutral
change. Do not borrow the unconstrained caches or batch settings from a
128 GB workstation example.

## Implementation-ready evaluation plan

1. **Establish the complaint.** Compare the user's original recording with its
   Piano.wav, volume matched. Add authorized recordings with exposed acoustic
   attacks, piano under vocals, reverb, electric piano, pads/strings/guitar and
   no piano. Separate acoustic-piano detection from broader keys extraction.
2. **Permission-supported pilot.** Re-export the original Mega53 native
   complex piano head. Shared front end plus twelve blocks plus one head is
   fourteen graphs, rather than the current nineteen-graph family export.
   Preserve original complex-mask inference and transform. Do not reuse the
   custom nonnegative family-energy projection as a piano model. Obtain the
   original omitted head weights at build time; they are not present in the
   currently bundled selected-head export. This pilot is a comparison point,
   not the promised fast default.
3. **Conditional candidates.** If commercial weight permission is resolved,
   compare BS-RoFormer SW six-stem with the acoustic-piano specialist. The
   six-stem route could replace the five-stem cascade with a single native
   multi-output model. Selecting just one saved stem from a joint model does
   not by itself remove all other output computation. Native six stems do not
   supply the extended strings/brass/synths family outputs.
4. **Profile the actual runtime.** Evaluate bounded MLX or cached Core ML
   CPU+GPU, preserving input context and output semantics. Measure on
   **M3 / 8 GB / macOS 26**, the packaged app, not Linux or Intel. Record cold
   and warm file-to-WAV times (including decode, load/compile and writing),
   peak process and GPU allocation, memory pressure/swap, cancellation and
   continued browsing/playback/chord analysis. Retain macOS 15 and Intel
   installer checks without treating them as GUI/model validation targets.
5. **Choose by audible and measured results.** Use volume-matched blind A/B
   listening for attacks, sustain, reverb, bleed and false piano. Where lawful
   ground-truth multitracks are available, record separation metrics on the
   same set. Report time/audio-duration and warm/cold results separately.
   Prefer faster-than-real-time as an initial product goal, not an existing
   benchmark. Reject a speed gain that introduces sustained swapping or erases
   attacks. Keep existing exports and background-job contracts compatible.

No checkpoint was downloaded, installed, converted or executed for this
research. No live inference, listening-quality result, M3 timing or native
packaged-app validation is claimed. Hugging Face MCP searches returned
unavailable; direct public author/repository/model-card sources were used.
Local evidence captures and fetch hashes are retained outside the app at
`/workspace/stem-research-2026-10-31/`.

## Primary sources

1. [Spleeter official configuration](https://github.com/deezer/spleeter/blob/master/spleeter/resources/5stems.json) and [bandwidth FAQ](https://github.com/deezer/spleeter/wiki/5.-FAQ).
2. [MVSEP algorithms and piano comparison](https://mvsep.com/en/algorithms).
3. [BS-RoFormer SW ONNX model card and provenance warning](https://huggingface.co/elicwhite/bs-roformer-sw-6stem-onnx).
4. [Core ML six-stem port, measurements and licensing section](https://github.com/jonkubis/BS-ROFO-SW-Fixed-CoreML).
5. [Mega53 original configuration](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems.yaml) and [creator's exact-weight MIT grant](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245#issuecomment-5834608838).
6. [Piano-small author model card and license](https://huggingface.co/tjpurdy/Piano-Separation-Model-small).
7. [SCNet paper](https://arxiv.org/abs/2401.13276), [published model comparison](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md) and [SCNet XL IHF permission inquiry](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/262).
8. [Demucs original author's current license discussion](https://github.com/adefossez/demucs#license) and [six-stem piano caveat](https://github.com/facebookresearch/demucs).
9. [MLX separation runtime](https://github.com/ssmall256/mlx-audio-separator) and [release validation/benchmark details](https://github.com/ssmall256/mlx-audio-separator/blob/main/docs/release-validation.md).
10. [Official ONNX Runtime CoreML provider options and caching](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html).
11. [Banquet / query-bandit](https://github.com/kwatcharasupat/query-bandit) and [author-linked weights/license](https://zenodo.org/records/13694558).
12. [SAM Audio official repository](https://github.com/facebookresearch/sam-audio) and [license](https://github.com/facebookresearch/sam-audio/blob/main/LICENSE).
