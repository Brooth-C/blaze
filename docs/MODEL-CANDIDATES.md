# Local Mac model candidates

These opt-in engines implement the first two experiments from the model research.
They are not enabled or bundled in stable releases. No default model was replaced.
Only Apple Silicon/macOS26 native performance validation is supported. Existing
Practice features, display-only chord transpose and Advanced Studio removal remain.

## ChordMini BTC CL

Implemented: pinned source/checkpoint converter, strict state and vocabulary
validation, ONNX logits, current-librosa CQT, raw-zero padding before checkpoint
normalization, 108-frame windows with54 stride and logit voting. Labels normalize
flat/sharp equivalents by pitch, preserving all170 indexes. Full-file analysis,
source-revision/cancellation boundaries and durable Store/cache integration work.
Result identity includes the model plus feature/decoder-contract hashes; old models
and corrected analyses keep their own IDs. Candidate scores are uncalibrated.

The upstream PyTorch reference and our actual ONNX output have equal winning
labels for synthetic logits, short/partial windows and a complete real WAV pipeline.
This proves implementation parity, not accuracy superiority on real songs.
The experimental path currently emits chords/key/waveform without neural beat or
meter analysis; it is an evaluation path, not a replacement for the full stable
analysis feature set. Audio loading/CQT cancellation is checked at phase boundaries;
those synchronous library calls are not instantly interruptible. Limit30 minutes.

Use an isolated Python environment with tools/model_candidates/requirements.txt.
Pin public source ptnghia-j/ChordMini at aa6e3a8d7b017f082fd2aaff9329d5c26af49c03.
The converter verifies the checkpoint SHA256 and rejects a dirty source checkout.

```sh
python tools/model_candidates/export_chordmini.py --source /absolute/ChordMini --output /absolute/candidates/chordmini
python tools/model_candidates/benchmark.py --kind chordmini --models /absolute/candidates/chordmini --source /absolute/song.wav --output /absolute/results/chordmini --runs 2
```

On a non-Mac evaluation machine, add --reference-cpu for reference correctness
runs only. Those numbers must not be described as Mac/GPU benchmarks.

To test this candidate in the local Mac app, start its source launcher in the same
isolated environment with BLAZE_EXPERIMENTAL_CHORDMINI_DIR pointing to the generated
directory. This explicitly substitutes the candidate for Mac's 'powerful' analysis
selection only. Unset the variable to restore the current strongest ensemble.
Other desktop presentations and other model selections retain their engines.
Missing/corrupt assets or dependencies produce an error, never silent fallback.

## Native Core ML SCNet

Implemented: checksum-pinned v0.1.2 release archive staging, recursive per-file
integrity validation against fixed hashes, native MLProgram load using CPU_AND_GPU,
actual signature/dtype discovery, bounded finite FP16 input conversion, cancellation
checks around native predictions and reuse of the existing four-stem streaming
normalization/overlap/WAV writer. Failure/cancellation cleans unfinished outputs.
Native prediction itself is synchronous: cancellation completes after the current
Core ML call returns. No claim of mid-call interruption or full-GPU operator coverage.

Download scnet_coreml.mlpackage.zip from:
https://github.com/demixr/scnet-executorch/releases/download/v0.1.2/scnet_coreml.mlpackage.zip

Expected archive SHA256:
d15357c0abc901defb76282178966b0c41cc3e7b9ad34a8a0fd4598b11043c2f

```sh
python tools/model_candidates/stage_native_scnet.py --archive /absolute/scnet_coreml.mlpackage.zip --output /absolute/candidates/native-scnet
python tools/model_candidates/benchmark.py --kind native-scnet --models /absolute/candidates/native-scnet --source /absolute/song.wav --output /absolute/results/native-scnet --runs 2
python tools/model_candidates/benchmark.py --kind scnet-current --models /absolute/current-stem-models --source /absolute/song.wav --output /absolute/results/current-scnet --runs 2
```

Set BLAZE_EXPERIMENTAL_SCNET_DIR to the staged directory when launching the local
Mac source app to test it for four-stem mode. It does not affect Piano/Backing,
five-stem or nine-stem selection. coremltools is a candidate-only dependency; the
stable app's bundle/dependencies are not silently expanded. A real macOS26 test and
package review are required before adding this engine to distributable artifacts.

The actual staged release was inspected: input mix_spec[1,4,2049,338], output
var_2176[1,4,4,2049,338], FP16 interface,12 native LSTM ops. That inspection can run
on Linux; native prediction cannot. No native speed/parity result is claimed here.
Retain existing upstream SCNet/export notices if incorporating the artifact in a
future distribution; exact checkpoint redistribution must be approved before shipping.

## Verification and acceptance

```sh
BLAZE_STEM_BACKEND=cpu BLAZE_TEST_NATIVE_SCNET_DIR=/absolute/candidates/native-scnet BLAZE_TEST_CHORDMINI_DIR=/absolute/candidates/chordmini BLAZE_TEST_CHORDMINI_SOURCE=/absolute/ChordMini python tests/Blaze-Model-Candidates-Tests.py
```

Real-model tests need the isolated reference dependencies. Base tests still run
without downloading models; real-model checks are explicitly skipped when absent.
Benchmark output includes source hash, model/contract provenance, total job time,
real-time factor, process-lifetime RSS and available phase/runtime records. Output
directories must be new. SIGINT cooperates with cancellation; failures leave a JSON
report. Existing benchmark_macos_stems.py retains detailed provider diagnostics.

Before promoting a candidate: measure cold/warm whole-song latency on M3/8GB,
actual memory pressure, concurrent playback/analysis, cancellation and quality on
held-out music. Inspect FP16 piano transients, weak signals, leakage and chord boundary
errors. Numerical export parity is not a musical quality benchmark. No candidate
checkpoint/artifact binaries should be committed to Git or automatically published.

Banquet piano and SubRoformer remain evaluation proposals: no verified piano-quality
win or Mac conversion has been established, so they are not added as default engines.
The next decision is based on measured model quality and native execution, not adding
more untested runtimes to the app.
