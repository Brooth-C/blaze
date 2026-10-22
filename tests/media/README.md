# Generated media fixture

`playback-avc-aac.mp4` contains three seconds of FFmpeg's synthetic `testsrc2`
pattern and a 440 Hz sine wave. It contains no third-party recording. The fixture
is provided under CC0-1.0 for playback tests and is not bundled with the app.

Generate it using FFmpeg with the libx264 encoder:

```sh
ffmpeg -y -f lavfi -i 'testsrc2=size=160x90:rate=10' \
  -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 3 \
  -c:v libx264 -profile:v baseline -pix_fmt yuv420p -preset ultrafast \
  -c:a aac -b:a 32k -movflags +faststart playback-avc-aac.mp4
```

Native package tests decode this AVC/AAC fixture in the actual platform webview,
including pixels, playback, seeking and returning to Studio. The Chromium-only
browser tests use a generated VP8/Opus WebM, since Chromium builds can omit
proprietary codec support.
