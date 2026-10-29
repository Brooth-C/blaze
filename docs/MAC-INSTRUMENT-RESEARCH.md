# Instrument families inside Blaze

## Goal and output contract

Retain the existing higher-quality five-stem pipeline and add a pass that refines
Other into guitar, strings, brass, synths and an unassigned residual. The full
workflow exports nine tracks, not thirteen and not 53. The first four existing
tracks remain byte-for-byte unchanged. Keep five-stem mode available because the
extended workflow is slower. Native validation uses macOS 26 and Apple Silicon;
no macOS 15 or Intel Mac test runners are scheduled.

## Model and commercial terms

Original checkpoint: `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`, from the
[creator's v1.0.21 release](https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21).
Size 1,368,919,887 bytes; SHA256
`c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f`.
Both size and hash match the original GitHub release metadata.

The [creator's explicit statement](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245#issuecomment-5834608838)
grants MIT rights for these 53-stem weights, including commercial use, conversion,
bundling and redistribution. Credit ZFTurbo and retain MIT notices. The author
does not own all training audio and supplies no warranty or indemnification;
the weight license is not a grant to users' input recordings.

The [author's model description](https://mvsep.com/algorithms/135) distinguishes
the published open checkpoint from the newer hosted service model, says that
specialists often perform better, and reports modest synth and generic-guitar
scores. Those published scores do not measure Blaze's grouped projection or
establish that every instrument will be detected or isolated cleanly.

## Selected heads and deployment

Retain the trunk and original independent mask estimators at indices **1, 16,
20, 37, 8 and 38**: acoustic-guitar, electric-guitar, guitar, strings, brass,
synth. The source constructs heads independently; selecting them does not modify
the shared representation or retained parameters. Unused heads are omitted.
Strict state-dictionary loading checks every retained parameter.

Use the source's inference context of **882000 samples** (20 seconds), stereo
44.1 kHz, periodic Hann FFT2048 with hop512, FP32 computation and 50% overlap.
The source configuration has a different training chunk size; do not confuse it
with the recommended inference context. The export is split into a front end,
twelve transformer blocks and six heads to release intermediate runtime arenas.
Torch is a build dependency only, not bundled with the application.

## Disjoint instrument-family outputs

Related guitar heads are max-pooled per spectral bin, never summed. Four
nonnegative family energy scores are divided by the larger of one and their
sum. Unclaimed mass becomes Other. Apply these real masks to the original
complex spectrum, preserving its phase; keep DC and numerical reconstruction
residual in Other. This prevents multiple families from each receiving a full
copy of the same bin and preserves an additive mix.

This projection intentionally differs from the original complex masks, so raw
model SDRs cannot be claimed for the resulting exports. The system always
offers four family estimates and a residual; it does not claim reliable
instrument-presence detection. Do not drop quiet tracks silently.

## Validation

Local conversion: selected-head maximum rewrite error **7.15e-7**. Production
ONNX raw-head parity against original-source masks: RMS **9.69e-9**, 99.9th
percentile **8.57e-8**, maximum **8.94e-7**. Peak Linux process RSS **2,744,968
KiB** (about 2.62 GiB), with approximately 212 seconds for a full 20-second
context including sequential session loading. This is not a Mac speed claim.
Publication requires RMS below 1e-5, 99.9th percentile below 1e-4 and Linux
inference RSS below 4 GiB. These gates verify conversion, not musical SDR.

Tests cover overlapping score normalization, silence, short clips and reflected
long-recording boundaries, exact durations, full-band reconstruction, retained
first-four WAV bytes, source preservation, cancellation and intermediate-file
cleanup. Browser tests cover nine exports, scrolling with persistent controls,
the five-stem alternative, authenticated downloads and the same Studio player.
Real bundled-model inference and native macOS 26 packaged-app checks gate the
application release.
