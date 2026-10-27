# Higher-quality local stem separation

Selection work started 2026-10-27. This document is an evaluation record, not a
claim that any model is universally strongest or that an unfinished build ships.

## Candidate selected for evaluation

ZFTurbo's BS-RoFormer four-stem checkpoint
`model_bs_roformer_ep_17_sdr_9.6568.ckpt`, release v1.0.12, SHA256
`3e9daecd70aaed5b5a0d1f861cc4d77eaa45afb3fc6301b1cf32c1be0f5868fb`.

- [Trainer's exact-checkpoint MIT grant](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/254#issuecomment-5914058767).
  The author asks for credit to **ZFTurbo**, provides no warranty, and explicitly
  leaves assessment of the MUSDB18-HQ training-data terms to commercial integrators.
  An MIT grant to weights is not indemnification or a legal clearance of training data.
- [Published comparable metrics](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/pretrained_models.md):
  reported MUSDB18-HQ average SDR 9.65; Multisong average 9.38. The existing
  SCNet Small entry reports 9.03 and 8.87 respectively. These are upstream results,
  not measurements of Blaze's implementation or a guarantee for every recording.
- Four native model outputs, in training order: drums, bass, other, vocals.
  **Piano is not a native output of this checkpoint.** A five-output pipeline
  needs a separate piano stage; that must be assessed independently.

## Candidates not selected

- SCNet XL IHF reports stronger multi-stem scores in the same table, but an exact
  checkpoint commercial-permission question is still unanswered in
  [issue 262](https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/262).
  Repository code MIT is insufficient evidence for the weights.
- BS-RoFormer SW six-stem ONNX: its own
  [model card](https://huggingface.co/elicwhite/bs-roformer-sw-6stem-onnx)
  says the weights were rehosted without a stated license and the rehoster did
  not train them or know their provenance. Its MIT metadata describes code
  lineage, not an established grant by the checkpoint creator.
- KimberleyJensen's Mel-Band RoFormer is a credible vocal specialist, with an
  [author-linked MIT model card](https://huggingface.co/KimberleyJSN/melbandroformer).
  It does not itself separate drums, bass or piano; adding it is a separate
  quality/performance tradeoff, not a replacement five-stem model.
- Original Demucs and noncommercial piano checkpoint restrictions remain as
  documented in [the piano research](MAC-PIANO-RESEARCH.md).

## Validation required before changing the shipped default

Retain the checkpoint's original 485100-sample (11-second) context and FP32
weights. Verify a Torch-free ONNX spectral export against the original model;
validate stereo transforms, source order, chunk boundaries, exact duration,
finite samples, cancellation and output cleanup. Measure actual Apple Silicon
runtime and memory using the packaged app. Preserve five exported WAVs and keep
the original source untouched. Do not silently fall back to a different model.

Initial original-model inference on this Linux workspace (two CPU threads) took
56.75 seconds for one full-context random-input chunk. This is not a Mac
benchmark and does not measure musical separation quality.

## Export validation

The original full-context model, its memory-bounded attention rewrite and the
sequential ten-graph export use identical checkpoint weights and FP32 compute.
One checkpoint is split into a front end, eight transformer blocks and output
heads; the application releases each block's runtime before advancing.

On the captured original-model spectral input, the production ONNX pipeline
produced maximum absolute mask error **6.2585e-7**, RMS **1.0492e-8**, and 99.9th
percentile error **7.1217e-8**. Gates are RMS below 1e-5 and 99.9th percentile below
1e-4. Peak process RSS was **2,285,296 KiB** (approximately 2.18 GiB), compared
with **7,599,780 KiB** for the single-graph loop export. CPU inference plus
sequential session loading took **87.33 seconds** on this Linux worker.
These are conversion/runtime measurements, not SDR or a Mac speed prediction.

The shipped graph files are individually checksum-pinned. Re-export using
`tools/roformer/export.py --msst <pinned-checkout> --checkpoint <original-file>
--output <new-directory>`. Build dependencies and the source revision are pinned
in the tool and assets module. Exported file hashes may differ with build paths
and exporter metadata; validate numerical equivalence before changing any pin.

Streaming tests cover recordings longer than two contexts, reflected global
borders, short zero-padded clips, stereo channel order, exact sample counts,
unity-gain reconstruction, cancellation and cleanup. Separate browser tests
cover progress, retry, five exports and the persistent playback element. Native
packaged-app checks remain required before a release is published.

The real five-output pipeline passed its eight-test local suite, including
actual BS-RoFormer and Spleeter inference. An actual cancellation completed in
1.43 seconds including setup, removed partial WAVs and preserved the source.
The packaging helper verified all ten blocks and copied their notices.
