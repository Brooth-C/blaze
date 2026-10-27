# Blaze for Mac 0.13.0

The main **Split stems → Separate five stems** action now uses a higher-quality
BS-RoFormer model for vocals, drums, bass and remaining music, followed by the
existing Spleeter piano extractor on that remaining music. The five separate
WAVs remain **Vocals, Drums, Bass, Piano and Other**. There is one action and no
model picker. **Isolate piano** remains available separately.

Everything runs locally on Apple Silicon. No audio upload, account or additional
model installation is required. This is a quality-focused pipeline with larger
bundled weights and longer processing times than the previous Spleeter-only
five-stem action. Progress and cancellation remain available. Each completed
track can be played in Studio or saved independently. The original recording is
preserved, including its stereo timing, relative gains and full-band residual.

This is not a native five-stem RoFormer: piano quality remains dependent on
Spleeter. Guitar, strings, brass and synths stay grouped into Other. Leakage and
artifacts remain possible. No claim is made that this is universally the world's
best separator or that it recreates original studio multitracks.

The exact BS-RoFormer checkpoint is MIT-licensed by its trainer, **ZFTurbo**;
the original notices, export provenance and checksum are bundled. The author
provides no warranty or training-data indemnification. See
[model selection and validation](MAC-STEM-QUALITY-RESEARCH.md) for sources and
comparison limits. Existing piano model and decoder notices remain included.

Only the Apple Silicon Mac application changes in this release.
