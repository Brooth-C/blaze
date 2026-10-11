#!/usr/bin/env bash
set -euo pipefail
ABI=${1:?Pass arm64-v8a or x86_64}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="$ROOT/../build/android-native-$ABI"
PACKAGE="$WORK/package"
NDK="$ANDROID_HOME/ndk/28.2.13676358"
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64"
case "$ABI" in
  arm64-v8a) ARCH=aarch64; TARGET=aarch64-linux-android; HOST=aarch64-linux-android ;;
  x86_64) ARCH=x86_64; TARGET=x86_64-linux-android; HOST=x86_64-linux-android ;;
  *) echo "Unsupported ABI" >&2; exit 1 ;;
esac
mkdir -p "$WORK/sources" "$PACKAGE/jniLibs/$ABI" "$PACKAGE/assets/licenses"
cd "$WORK/sources"
curl -fL --retry 3 https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz -o ffmpeg-9.0.2.tar.xz
curl -fL --retry 3 https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz.asc -o ffmpeg-9.0.2.tar.xz.asc
curl -fL --retry 3 https://ffmpeg.org/ffmpeg-devel.asc -o ffmpeg-devel.asc
mkdir -m 700 -p "$WORK/gnupg"
gpg --homedir "$WORK/gnupg" --batch --import ffmpeg-devel.asc
gpg --homedir "$WORK/gnupg" --batch --status-fd 1 --verify ffmpeg-9.0.2.tar.xz.asc ffmpeg-9.0.2.tar.xz | tee "$WORK/signature.txt"
grep -q 'VALIDSIG FCF986EA15E6E293A5644F10B4322F04D67658D8' "$WORK/signature.txt"
curl -fL --retry 3 https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz -o lame-3.100.tar.gz
echo 'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e  lame-3.100.tar.gz' | sha256sum -c -
curl -fL --retry 3 https://codeload.github.com/quickjs-ng/quickjs/tar.gz/6d46d07d04041b40f4f49eaa7fdebe44c314c699 -o quickjs-0.17.0.tar.gz
tar -xf ffmpeg-9.0.2.tar.xz
tar -xf lame-3.100.tar.gz
mkdir -p quickjs
tar -xf quickjs-0.17.0.tar.gz --strip-components=1 -C quickjs
cp ffmpeg-9.0.2/COPYING.LGPLv2.1 "$PACKAGE/assets/licenses/FFMPEG-LGPL.txt"
cp lame-3.100/COPYING "$PACKAGE/assets/licenses/LAME-LGPL.txt"
cp quickjs/LICENSE "$PACKAGE/assets/licenses/QUICKJS-MIT.txt"
cp "$ROOT/native/README.md" "$PACKAGE/assets/licenses/NATIVE-NOTICES.txt"
cp "$ROOT/native/build.sh" .
tar -czf "$WORK/Blaze-Android-Native-Sources.tar.gz" ffmpeg-9.0.2.tar.xz ffmpeg-9.0.2.tar.xz.asc ffmpeg-devel.asc lame-3.100.tar.gz quickjs-0.17.0.tar.gz build.sh
if [ ! -f "$PACKAGE/jniLibs/$ABI/libblaze_ffmpeg.so" ]; then
  PREFIX="$WORK/lame-prefix"
  export CC="$TOOLCHAIN/bin/${TARGET}24-clang" AR="$TOOLCHAIN/bin/llvm-ar" RANLIB="$TOOLCHAIN/bin/llvm-ranlib"
  export CFLAGS='-O2 -fPIC' LDFLAGS='-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384'
  cd "$WORK/sources/lame-3.100"
  ./configure --host="$HOST" --prefix="$PREFIX" --disable-shared --enable-static --disable-frontend --disable-decoder --disable-nasm
  make -j4
  make install
  cd "$WORK/sources/ffmpeg-9.0.2"
  ./configure --target-os=android --arch="$ARCH" --enable-cross-compile --cc="$CC" \
    --ar="$AR" --ranlib="$RANLIB" --strip="$TOOLCHAIN/bin/llvm-strip" --enable-pic \
    --disable-shared --enable-static --disable-doc --disable-debug --disable-autodetect --disable-x86asm \
    --disable-gpl --disable-nonfree --disable-version3 --disable-everything --enable-ffmpeg --enable-ffprobe \
    --enable-avcodec --enable-avformat --enable-avfilter --enable-swresample --enable-swscale \
    --enable-protocol=file,pipe --enable-libmp3lame --enable-encoder=libmp3lame,aac,flac,pcm_s16le \
    --enable-decoder=aac,aac_latm,mp3,mp3float,flac,vorbis,opus,alac,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,h264,hevc,av1,vp8,vp9 \
    --enable-parser=aac,aac_latm,mpegaudio,flac,opus,vorbis,h264,hevc,av1,vp8,vp9 \
    --enable-demuxer=mov,matroska,mp3,aac,ogg,flac,wav,mpegts,concat,ffmetadata \
    --enable-muxer=mp4,mov,matroska,webm,mp3,ipod,wav,flac,ogg,adts,mpegts,ffmetadata \
    --enable-filter=aresample,aformat,anull,abuffer,abuffersink,null,buffer,buffersink \
    --enable-bsf=aac_adtstoasc,extract_extradata,h264_mp4toannexb,hevc_mp4toannexb \
    --extra-cflags="-I$PREFIX/include -O2 -fPIC" --extra-ldflags="-L$PREFIX/lib $LDFLAGS" --extra-libs='-lm'
  make -j4 ffmpeg ffprobe
  cp ffmpeg "$PACKAGE/jniLibs/$ABI/libblaze_ffmpeg.so"
  cp ffprobe "$PACKAGE/jniLibs/$ABI/libblaze_ffprobe.so"
fi
if [ ! -f "$PACKAGE/jniLibs/$ABI/libblaze_qjs.so" ]; then
  cmake -S "$WORK/sources/quickjs" -B "$WORK/qjs-build" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM=android-24 -DCMAKE_BUILD_TYPE=Release \
    -DQJS_BUILD_EXAMPLES=OFF -DCMAKE_EXE_LINKER_FLAGS='-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384'
  cmake --build "$WORK/qjs-build" --target qjs_exe -j4
  cp "$WORK/qjs-build/qjs" "$PACKAGE/jniLibs/$ABI/libblaze_qjs.so"
fi
"$TOOLCHAIN/bin/llvm-strip" "$PACKAGE/jniLibs/$ABI/"*.so
printf 'FFmpeg 9.0.2; LAME 3.100; QuickJS-ng 0.17.0; NDK 28.2; API 24; LGPL-only media build\n' > "$PACKAGE/assets/licenses/NATIVE-BUILD.txt"
