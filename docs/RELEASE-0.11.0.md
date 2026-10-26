# Blaze for Apple Silicon 0.11.0 — piano isolation

Music Studio adds **Isolate piano** alongside the existing four-stem split.
Open a recording, click **Split stems**, then choose **Isolate piano**. The app
saves **Piano.wav** and **Accompaniment.wav**, with progress, cancellation,
playback in the existing player, individual WAV export and Open folder.
Accompaniment is the original recording minus the estimated piano, preserving
its full bandwidth. Piano extraction uses the original five-stem Spleeter
model with its standard 11 kHz modeled band. It estimates piano already present
in a recording; it does not generate a piano arrangement. Bleed and artifacts
can remain, especially with layered keyboards and instruments with similar timbre.

The existing SCNet four-stem workflow is retained. Piano isolation runs the five
Spleeter spectral graphs sequentially to bound memory, then reproduces the
original joint softmax and power-2 ratio mask. It is one Spleeter model, not an
ensemble. Processing stays on the device and all model files are bundled.

Deezer's authors explicitly describe the source and pretrained models as
MIT-licensed in their [JOSS paper](https://doi.org/10.21105/joss.02154).
The repository README specifically mentions code; the release retains both
that provenance and the paper as the basis for using the official weights.
The conversion code is Apache-2.0. Both license texts, the conversion notice,
source URLs and checksum pins accompany the model. No non-commercial-only
piano checkpoint or Demucs weights are included. Rights to source recordings
remain separate from model licensing.

The ONNX export is pinned to matthewbae/spleeter-onnx-models release
`spleeter-5stems-onnx-v1`, revision `1215fccebccf416ecd02fa7e08ed74413b15015f`.
Its official source archive is Deezer Spleeter v1.4.0 `5stems.tar.gz`, SHA-256
`25a1e87eb5f75cc72a4d2d5467a0a50ac75f05611f877c278793742513cc7218`.
Independent comparison against that TensorFlow checkpoint validates the piano
mask conversion; synthetic tests establish runtime contracts, not piano quality
on every song. TensorFlow is used only for independent verification and is not
bundled in Blaze.

Apple Silicon only, macOS 13 or newer. This normal Mac release has its own
download; other-platform packages and the combined v4.5.0 Latest distribution
remain unchanged. The app is ad-hoc signed and is not Apple-notarized.
