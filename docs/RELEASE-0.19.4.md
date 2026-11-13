# Blaze for Mac 0.19.4

Practice keeps your chords visible and makes transposing them immediate.

- The chord guide stays above the scrolling controls, including in compact windows.
- Transpose changes displayed chords and key without interrupting audio. Audio pitch
  is a separate optional control, off by default. WAV exports follow audio pitch;
  Piano and Backing can still download together as two separate WAV files in a ZIP.
- Saved practices remember chord transpose and audio pitch independently. Older
  practices retain their notation setting and open with original audio pitch.
- Practice avoids repeated unchanged control updates, moves the playhead with a
  compositor transform and reduces background polling when idle or hidden.
- Saved chord analyses skip neural-session initialization. New analysis avoids a
  duplicate recording read and prepares waveform peaks more efficiently.
- Separation packs spectral features with fewer temporary allocations and skips
  padding-only model passes that cannot contribute to saved audio. Existing model
  weights, precision and GPU defaults remain in use.

Local reference/browser tests verify these changes. Individual processing-step
measurements are not claims of whole-song speed on a particular Mac.

The source also includes explicit local evaluation adapters for ChordMini BTC CL
and native Core ML SCNet, with conversion and benchmark tools. They are disabled
by default; their model binaries and optional dependencies are not included in
this release. They have not been established as faster or more accurate on M3.

Advanced Studio remains excluded. Windows, Linux and Android releases are unchanged.
