# Blaze macOS decoder: corresponding source and rebuild recipe

Blaze runs FFmpeg and ffprobe as separate, replaceable command-line executables.
Blaze does not link the FFmpeg libraries into its own application. The supplied
executables use FFmpeg 7.1.3 with GPL, nonfree and version 3 components disabled.
The build retains all default decoders and demuxers; encoders are restricted to
AAC, FLAC, PCM, MP3, Opus, Vorbis, PNG and Motion JPEG. HTTPS uses Apple's
Secure Transport; PNG compression uses Apple's system zlib. Static codec
dependencies are built from the exact included
archives rather than discovered from a Homebrew installation.

FFmpeg: LGPL 2.1 or later. LAME 3.100: LGPL 2.0 or later (encoder library only;
frontend and decoder disabled). Ogg 1.3.5, Vorbis 1.3.7 and Opus 1.5.2: BSD
licences. Their copyright notices and complete licence texts are included under
`licenses/` and in the original source archives. The sources are unmodified.
Blaze's own licence and restrictions do not apply to these third-party sources.

## Rebuild on a Mac

Use an Apple Silicon Mac for an arm64 executable, or an Intel Mac for an x86_64
executable. This is a native build, not a universal-binary or cross-compile
recipe. It targets macOS 13 or later without CPU-specific `-march=native` flags.
Both architectures use the same verified source versions and configure options.

1. Extract this archive into an empty writable directory.
2. Install Apple's Xcode command-line tools and ensure `xcrun`, `make`, `awk`,
   `otool` and `xcodebuild` are available. Use Python 3.12+, CMake 3.20+ and
   pkg-config. CMake and pkg-config are build tools only and are not shipped.
3. Run `python3 fetch_sources.py --offline`. This verifies every included source
   archive's SHA256 and size and safely extracts it. Without `--offline`, missing
   archives can be downloaded from the original URLs; hashes remain mandatory.
4. Run `sh build.sh`. The recipe compiles static codec libraries using Apple
   clang and then builds `output/bin/ffmpeg` and `output/bin/ffprobe`. Set
   `BLAZE_CODEC_JOBS` to change the default four parallel jobs if needed.
5. The script rejects any non-system dynamic dependency and packages matching
   sources automatically into `output/FFmpeg-LGPL-Corresponding-Sources.zip`.
   The `output/decoder-manifest.json` records both executable hashes and the
   corresponding-source archive hash. The output also includes licence texts.

Exact configure options are retained in `output/buildconf.txt` and
`output/config.mak`; detection output is in `output/config.log`, toolchain
versions are in `output/toolchain.txt`, and build logs are under `logs/`.
Compiler/SDK paths recorded in those files describe the original build host;
the rebuild script discovers the current Mac's Apple toolchain instead of
requiring those original paths. A different compiler or SDK may produce
different executable hashes from the included original manifest.

The recipe requires no administrator privileges during the build, makes no
global PATH changes and never uses Homebrew multimedia libraries. The compiled
executables dynamically reference only macOS system frameworks and runtime
libraries. Modified executables rebuilt from these sources can replace the
bundled `ffmpeg` and `ffprobe` files in `Blaze.app/Contents/Resources/bin/`;
adhoc-sign the modified application if macOS requires its bundle seal updated.

Upstream licence and build information:
- https://ffmpeg.org/legal.html
- https://ffmpeg.org/platform.html
