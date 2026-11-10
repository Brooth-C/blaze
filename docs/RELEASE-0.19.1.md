# Blaze for Mac 0.19.1

This update reduces repeated work during stem separation while preserving the
existing models, full FP32 piano inference, chunk lengths, overlap, gain and
output formats.

- Piano isolation submits attention without an immediate CPU wait, combines
  the Q/K rotary calculation, compiles its parameterised feed-forward subgraph
  for operator fusion and reuses the bounded Metal buffer cache between
  transformer layers. Cancellation checkpoints and final GPU cleanup remain.
- RoFormer, instrument and Spleeter Core ML paths reuse up to two small verified
  sessions per job, with a 32 MiB admission budget for serialized weights. Large
  sessions remain disposable; all retained sessions close when a job ends.
- Waveform reconstruction reuses its window-normalisation envelope across
  channels, stems and chunks, avoiding repeated overlap calculations and large
  repeated-window allocations.
- The existing Mac benchmark reports ONNX session creation and reuse counts.
  A separate full-context Metal benchmark compares the released and updated
  evaluators using warm-ups followed by two ABBA rounds on the same device.

The retained-session weight budget and Metal buffer-cache limit are not caps
on total memory or Core ML's internal buffers. GPU defaults and the Practice
workflow are retained. This release targets Apple Silicon and macOS 26 checks;
other platform releases are unchanged.

Original-checkpoint numerical parity and regression tests validate correctness.
A local Linux CPU benchmark of warm 20-second stereo inverse spectral
reconstruction produced bit-identical audio and reduced median stage time from
0.1317 to 0.1080 seconds (about 18%). This is a DSP-stage measurement, not an
end-to-end separation speedup or an M3 result. Physical M3/8 GB timing, memory
pressure, listening quality and comparison with Logic still require measurement.
