# Blaze for Mac 0.18.1

Fixes the Beat This! rhythm model's ONNX Slice error during chord analysis on
the Core ML path. Each rhythm context now compiles with its exact frame count,
resolving the dynamic scalar slice bounds before execution. Model weights,
audio contexts and overlap handling are preserved.

GPU inference remains the Apple Silicon default: MLX/Metal for piano isolation
and Core ML CPU/GPU for other ONNX models. Shape-specific Core ML cache entries
prevent compiled rhythm contexts from being reused with incompatible lengths.

The macOS 26 release checks now run the actual Beat This! checkpoint through
Core ML at short, partial and full context lengths and compare it with the
dynamic CPU reference. Profiling verifies that Core ML partitions execute;
hosted checks do not establish physical M3 GPU placement or performance.

Studio also gains a deeper graphite palette, gentler panel separation and
calmer track colours. The waveform editor inherits its selected track's hue,
and capsule toolbar groups follow the current Logic Pro 13 reference. Blaze's
existing playback, analysis, separation and export commands remain connected.
The audited text/background palette pairs meet WCAG AA contrast.
