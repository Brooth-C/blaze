# Blaze instrument-family model assets, version 1

These are build assets, **not an application download**. The Mac application is
published separately after native macOS 26 validation.

Credit: **ZFTurbo**. This is a selected-head FP32 ONNX export of the published
MVSep Mega 53 open checkpoint, release v1.0.21. It preserves the shared trunk and
the independent acoustic-guitar, electric-guitar, guitar, strings, brass and
synth mask heads. Unused heads are omitted; retained parameters are unchanged.
One model is split into sequential blocks to bound runtime memory, retaining
the author-recommended 20-second input context.

The creator explicitly permits commercial use, redistribution, conversion and
bundling under MIT:
https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/245#issuecomment-5834608838.
There is no warranty or training-data indemnification. Included notices retain
the original architecture, source and adapted spectral-port attributions.

Original checkpoint SHA256:
`c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f`.
`models.json` lists every graph's hash, size and tensor contract; `export.json`
records the original selected indices and conversion; `validation.json` records
parity against original-source outputs and the memory gate.

Blaze converts the selected heads' evidence into bounded family masks with a
separate residual. This application projection is not identical to the raw
complex-valued model output. Numerical conversion parity is not a new musical
accuracy benchmark. The model is the published open version, not the newer
hosted MVSep service model, and it can leave bleed or miss notes.
