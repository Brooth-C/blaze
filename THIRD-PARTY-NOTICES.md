# Third-party software

The [Blaze Free-Use License](LICENSE.txt) applies only to Blaze's own code
and documentation. It does not replace the licenses of dependencies or
downloaded runtime tools. Their upstream projects provide license notices,
source code and redistribution requirements:

| Component | Upstream source and license information |
| --- | --- |
| Python | https://github.com/python/cpython |
| Managed Python builds | https://github.com/astral-sh/python-build-standalone |
| uv | https://github.com/astral-sh/uv |
| yt-dlp | https://github.com/yt-dlp/yt-dlp |
| Rich | https://github.com/Textualize/rich |
| Mutagen | https://github.com/quodlibet/mutagen |
| imageio-ffmpeg | https://github.com/imageio/imageio-ffmpeg |
| FFmpeg | https://ffmpeg.org/legal.html |
| aria2 | https://github.com/aria2/aria2 |
| Linux aria2 builds | https://github.com/abcfy2/aria2-static-build |

Installers download these tools separately. Exact versions and builds may
have different obligations; consult the notices supplied with each installed
component before redistributing it. Blaze's portable Mac aria2 release
includes the upstream source archive and GPL license with its binary assets.

The standalone Android APK embeds Python and yt-dlp using Chaquopy (MIT), and
uses AndroidX Core (Apache 2.0). These components are covered by their own
licenses, not Blaze's reserved rights. Complete notice files are included in
the APK's assets and in the [Android project](https://github.com/Brooth-C/blaze/tree/main/android/app/src/main/assets); the app's About dialog summarizes them.
The APK preview does not bundle FFmpeg or aria2.
