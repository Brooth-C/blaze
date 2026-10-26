# Blaze for Apple Silicon 0.12.0 — five separate stems

In Music Studio, choose **Split stems → Separate five stems** to save five
individual tracks: **Vocals.wav**, **Drums.wav**, **Bass.wav**, **Piano.wav** and
**Other.wav**. Play each in Studio, save individual WAVs, or reveal the complete
output folder. Progress and cancellation are included. The original recording
is preserved.

This is the standard five-stem grouping. Guitar, strings, brass, synths and
other remaining instruments are grouped into **Other**, rather than exported
as individual additional instrument types. **Isolate piano** remains available
for a piano track plus accompaniment.

The five-stem action uses the same bundled Spleeter five-stem model validated
in Mac 0.11.0, now saving every estimate. It runs locally using the five spectral
graphs sequentially. No account, cloud service or separate model download is
required. The earlier SCNet four-stem API is retained for compatibility.

The original model estimates frequencies below approximately 11 kHz. Higher
frequencies and numerical reconstruction residual are retained in **Other**, so
the five exports at unity gain sum back to the input recording. This preserves
the mix; it does not establish perfect isolation or separation quality. Bleed,
missing weak parts and artifacts can remain.

The authors' [JOSS paper](https://doi.org/10.21105/joss.02154) explicitly includes
Spleeter pretrained models in its MIT distribution statement. Model checksums,
source provenance, original MIT notice, Apache conversion license and notices
remain bundled. See [the model research](MAC-PIANO-RESEARCH.md) for the selection
and licensing evidence. No non-commercial-only model was added. Rights to
recordings remain separate from model licensing.

Validation includes actual five-output inference, original-checkpoint reference,
full-band reconstruction across chunk boundaries, saved lengths, authenticated
exports and source preservation. Native macOS 15 and 26 package checks require
all five WAVs, playback and piano-only isolation. Apple Silicon only, macOS 13
or newer. This is a normal Mac release; the combined v4.5.0 Latest distribution
and other-platform packages remain unchanged. Ad-hoc signed, not Apple-notarized.
