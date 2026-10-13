# Blaze for Windows 0.6.0

Blaze now integrates its audio/video downloader with offline Music Studio and Library.
The Windows player uses the original Blaze logo, a fixed window layout, a smoothly
scrolling chord strip, readable piano/guitar diagrams and compact import controls.

The default advanced engine combines verified MIT pretrained models with sequence
decoding, richer chord components and bass evidence. Beat/downbeat detection aligns
bar lines automatically where the grouping is consistent. Manual timing and chord
corrections are retained. Uncertain chord labels are hidden from the interface and
remain in exports. Recognition is fallible and has no real-song accuracy guarantee.

The Windows ZIP includes a replaceable LGPL-only FFmpeg decoder and its matching
sources/build recipe. No microphone, account, model training, cloud inference or
runtime model download is needed. Internet access is needed for online downloading.

Extract the whole ZIP and run `Blaze.exe`. Windows x64 and Microsoft Edge WebView2
Runtime are required. Keep `_internal` beside the executable. Download formats include
MP3, WAV, FLAC, M4A, Ogg and Opus; video quality depends on the source, with tested
4K passthrough. Transposition changes chord labels, not playback pitch.

YouTube sign-in/bot-check restrictions are not fixed by this update. Terminal installers
and the Android preview are separate release artifacts; this is the Windows GUI update.
