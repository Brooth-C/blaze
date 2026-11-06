# Apple Logic Pro Stem Splitter: model evidence

Research checked 31 October 2026. Scope: Apple's public documentation and
research, rather than extracting installed proprietary models.

## Answer

Apple calls the feature **Stem Splitter**. The official sources below describe
AI-assisted separation on the device, powered by Apple silicon, but do not name
the deployed network, publish its architecture or link downloadable weights.
I did not find a public identification of the exact model in the targeted
Apple documentation, developer and machine-learning research searches.

Consequently, calling it Demucs, Spleeter, SCNet, BS-RoFormer or a generic
Apple Intelligence language model would be speculation. The feature's product
name is not a published model identifier. This is a bounded research finding,
not proof that no relevant disclosure could exist elsewhere.

## What the primary sources establish

| Source | Evidence | What it does not establish |
| --- | --- | --- |
| [Apple's May 2024 launch](https://www.apple.com/newsroom/2024/05/logic-pro-takes-music-making-to-the-next-level-with-new-ai-features/) | Four initial parts: vocals, drums, bass and other; processing on the device, using AI and M-series silicon. | Architecture, model weights, parameter count, training set or exact hardware execution path. |
| [Apple's May 2025 update](https://www.apple.com/newsroom/2025/05/logic-pro-amplifies-beat-making-on-mac-and-ipad-with-advanced-new-capabilities/) | Adds guitar and piano, quality improvements, presets and custom submixes. | Which network or training change produced those improvements. |
| [Logic product page](https://www.apple.com/logic-pro/) | Documents six musical parts: vocals, drums, bass, guitar, piano and other. | Separation of every instrument into an individual track. |
| [Apple's 27 October 2026 announcement](https://www.apple.com/newsroom/2026/10/apple-creator-studio-adds-powerful-new-ai-features-and-even-more-creative-tools/) | Announces an enhancement for isolating/replacing/rebalancing drum parts; availability stated for November. | A named underlying separation network, weights or an already-shipped October release. |

The October announcement also describes a new assistant and a Liquid Glass
design. Its assistant-model discussion must not be used to identify the audio
separator. Announced November features must not be reported as already available
on this research date. The previously approved Blaze appearance remains based
on the current 12.4 listing reference; this research does not silently switch
the approved design to an announced future version.

## Relevant Apple research is not product attribution

[Resource-constrained Stereo Singing Voice Cancellation](https://machinelearning.apple.com/research/resource-constrained)
(February 2024, ICASSP) studies efficient removal of singing voice from stereo
audio. It adapts a small mono speech-separation network for stereo processing
and discusses limited compute, memory and look-ahead, with objective and
listening evaluation.

That establishes relevant Apple source-separation research. The page does not
state that its model is Logic's Stem Splitter. Vocal cancellation also differs
from jointly extracting six musical stems. The paper is therefore useful
background, not an identification of the shipping model.

## Consequences for Blaze

- Keep the existing audited, pinned local models. Do not substitute an
  unverified download advertised as Apple's model.
- Current code uses `QualityFiveStemSeparator` (BS-RoFormer followed by piano
  extraction), and `NineStemSeparator` refines Other into guitar, strings,
  brass, synths and a residual. The four-stem option uses SCNet. These are
  Blaze's implementations, not Apple's model.
- More output labels do not prove better separation. No controlled
  head-to-head listening/SDR comparison with Logic was performed here.
- Model licensing and commercial redistribution must be established for each
  actual checkpoint; Apple's product screenshots and research descriptions
  are not permission to redistribute its software or weights.
- UI integration in this change leaves separation models, precision,
  cancellation, cached assets and worker scheduling unchanged.

The US and regional Apple Support Stem Splitter guide URLs were also searched.
Some full-page fetches returned errors/rate limits, so the conclusions above use
the accessible Apple Newsroom, product and research pages directly. Search
results about third-party Core ML or MLX stem apps are not evidence of what
Logic itself uses.
