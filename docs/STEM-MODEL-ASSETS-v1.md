# Blaze BS-RoFormer model assets, version 1

These are model assets for Blaze's build workflow, **not an application download**.
The app release is published separately after native packaged-app checks pass.

This release contains an FP32 ONNX export of ZFTurbo's
`model_bs_roformer_ep_17_sdr_9.6568.ckpt` four-stem checkpoint. All ten `.onnx`
files are sequential parts of **one model**, retaining its full 11-second
context. They are not ten different models. `models.json` records each file's
SHA256, byte count and tensor shapes. Input is stereo 44.1 kHz spectral data;
native output order is drums, bass, other, vocals. Piano extraction is a separate
step in Blaze, not an output added to these weights.

Credit: **ZFTurbo**. The trainer's exact-checkpoint MIT grant is
https://github.com/ZFTurbo/Music-Source-Separation-Training/issues/254#issuecomment-5914058767.
The checkpoint is provided as-is; the author gives no warranty or training-data
indemnification. Included notices cover the training code, architecture and
adapted spectral port. Original checkpoint SHA256:
`3e9daecd70aaed5b5a0d1f861cc4d77eaa45afb3fc6301b1cf32c1be0f5868fb`.

Export sources and instructions are in `tools/roformer/`. Numerical conversion
validation and selection limits are documented in
`docs/MAC-STEM-QUALITY-RESEARCH.md`. These conversion checks do not constitute a
new SDR benchmark or establish superiority for every song or instrument.
