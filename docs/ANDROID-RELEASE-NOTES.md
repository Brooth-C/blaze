# Blaze Android advanced chords and Live Chord Flow preview

Music Studio stays inside Blaze, alongside the existing audio/video downloader and player. The default offline analyser now uses the pretrained BTC-170 model, without training or cloud inference.

Supported recognition: major/minor, diminished/augmented, sixths, sevenths (including half-diminished), sus2 and sus4. Ninths, elevenths and thirteenths are available as manual corrections; they are not automatically detected. N means no chord and X means uncertain. Scores are uncalibrated; real-song accuracy is not benchmarked.

Live Chord Flow shows four equal measures with proportional chord regions and one continuous progress line per measure, driven by LibVLC playback time. Rhythm settings support estimated beat timestamps or a manual tempo/meter/alignment, compound meter, later meter changes, and reverting to the original analysis. Meter/downbeats are not detected; until confirmed, neutral timing windows are shown. Corrections persist locally independently of the analysis cache.

Version code 8 uses the same signing key as Studio test.1 and test.2. Install over those previews to retain app data. Earlier CI previews may use a different key.

Verification: Android compile, lint and app/test APK builds; native Java timing/chord/signal tests; JavaScript timing tests; local extended-model inference and persistence checks. Device instrumentation and real-song accuracy testing remain outstanding. This does not fix YouTube sign-in/bot-check failures.

The native decoder/player engines are unchanged. Corresponding source is available from the Android v0.4.0 preview native-source archive. BTC and ONNX Runtime notices are included in the APK. No microphone permission, account or remote inference is used.
