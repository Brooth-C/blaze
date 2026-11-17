# Blaze for Mac 0.19.6

Lower processing memory pressure and clearer Practice controls.

- Chord analysis releases completed baseline and rhythm models earlier and runs the five-model ensemble with one live inference session at a time. Normal-length recordings reuse packed model inputs.
- Piano inference batches independent sequences on Macs with 8 GB memory while preserving full attention context, FP32 weights and overlap settings.
- Spectral analysis and audio reconstruction use bounded FFT batches. Piano buffers are released before reconstruction, and tuning interpolates only the peaks it uses.
- Practice has consistent expandable audio/download controls, visible keyboard focus for selectors and menus, and disclosure animations that respect reduced motion.
- Local diagnostic logs record analysis stages, Metal inference timing and allocation measurements.

Regression checks compare original numerical outputs, including byte-identical spectral and reconstruction fixtures. Component CPU improvements do not establish whole-song speed on a physical M3. The Metal benchmark compares with 0.19.5 and checks original-model output accuracy.

Explore and Practice remain the supported interface. Advanced Studio stays excluded. This release is Apple Silicon only; other platform releases remain available unchanged.
