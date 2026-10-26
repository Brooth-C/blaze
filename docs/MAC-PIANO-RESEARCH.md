# Piano isolation decision

The goal is to isolate piano already present in a recording, locally on Apple
Silicon, while retaining the existing four-stem separation. A piano arrangement,
MIDI transcription and synthesized replacement audio are different features.
Commercial use is a requirement for selecting the new bundled model.

| Candidate | Primary evidence | Decision |
| --- | --- | --- |
| tjpurdy Piano-Separation-Model-small | [Author model card](https://huggingface.co/tjpurdy/Piano-Separation-Model-small) specifies CC BY-NC 4.0. | Excluded from this commercial-compatible build. |
| Demucs six-stem weights | [Author README](https://github.com/facebookresearch/demucs) warns about piano quality; [author's weight-license clarification](https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611) limits weights to scientific use. | Excluded; the MIT code license does not establish commercial rights to its weights. |
| BS-RoFormer SW / community piano exports | Architecture/code licensing and mirrors alone do not establish a grant from the checkpoint creator. | Not selected without verified weight provenance and commercial terms. |
| Official Spleeter five-stem checkpoint | [Authors' JOSS paper](https://doi.org/10.21105/joss.02154) explicitly describes source and pretrained models as MIT-licensed. [Official configuration](https://github.com/deezer/spleeter/blob/master/spleeter/resources/5stems.json) includes piano. | Selected for the new piano action, retaining MIT attribution and conversion notices. |

Spleeter's README names code specifically, whereas its authors' paper covers
weights too. [Issue 898](https://github.com/deezer/spleeter/issues/898) requests
additional clarification; no separate maintainer reply was found. The explicit
published statement by the authors is the basis for this selection, not a claim
that a mirror's license label establishes permission or that a general legal
audit of every existing Blaze dependency has been completed.

Implementation uses the pinned five-graph logit export from
[matthewbae/spleeter-onnx-models](https://github.com/matthewbae/spleeter-onnx-models/tree/1215fccebccf416ecd02fa7e08ed74413b15015f).
The five U-Nets form one jointly normalized Spleeter model. All are needed to
reproduce its joint softmax and power-2 ratio mask; running only the piano graph
would produce the wrong result. Graphs run sequentially, with two CPU threads,
to limit memory. NumPy performs periodic-Hann STFT, inverse overlap-add and
cross-chunk blending; ONNX Runtime performs inference. No TensorFlow or PyTorch
runtime is added to the application.

Independent verification loaded Deezer's checksum-verified TensorFlow checkpoint
and compared converted piano masks on deterministic input. The measured mean
absolute difference was 5.24e-8, with maximum 0.000995; 64 nontrivial reference
points are retained in tests/media/piano-reference.json. This checks conversion,
not perceptual superiority. Runtime tests verify duration, stereo output,
reconstruction, cancellation and source preservation. Native package checks
require actual model execution and Piano.wav playback in WKWebView.

The piano estimate retains the official model's approximately 11 kHz modeled
band. Accompaniment is the original minus piano, preserving the source's full
bandwidth and relative gains. Four-stem SCNet remains unchanged; neither model
is represented as universally best. Piano can contain bleed, omit weak notes,
or confuse other keyboards and similar instruments. Recordings retain their
own rights independently of software and model licensing.
