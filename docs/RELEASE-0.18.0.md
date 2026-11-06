# Blaze for Mac 0.18.0

Studio opens with a refined Logic-inspired workspace, with the arrangement,
track controls, transport and selected-track editor aligned for Mac use.

On Apple Silicon, piano isolation uses MLX and Metal by default. Other ONNX
model inference requests Core ML CPU/GPU execution for stem separation, chord
recognition and rhythm analysis. Core ML may place unsupported operations on
CPU; audio decoding and spectral preparation also remain CPU work.

The app continues to use its existing search, playback, analysis and separation
engines. This release does not change the Windows, Linux or Android builds and
does not add an Intel Mac app.

Studio and the packaged Apple Silicon app are validated on macOS 26. GPU
placement and performance should still be checked on physical Apple Silicon
hardware; the hosted Mac runner is not an M3 device.
