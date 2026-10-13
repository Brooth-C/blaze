#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PREFIX="$ROOT/prefix"
mkdir -p "$ROOT/logs" "$PREFIX" "$ROOT/output"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export CFLAGS='-O2 -std=gnu11'
export CXXFLAGS='-O2'
export PATH_SEPARATOR=';'
export CC=gcc.exe AR=ar.exe RANLIB=ranlib.exe AWK=awk.exe
export GREP=grep.exe SED=sed.exe NM=nm.exe STRIP=strip.exe LD=ld.exe OBJDUMP=objdump.exe
export EGREP='grep.exe -E' FGREP='grep.exe -F'
JOBS=${BLAZE_CODEC_JOBS:-4}

build_cmake() {
    name=$1
    shift
    cmake -S "$ROOT/src/$name" -B "$ROOT/build/$name" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCMAKE_PREFIX_PATH="$PREFIX" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF "$@"
    cmake --build "$ROOT/build/$name" --parallel "$JOBS"
    cmake --install "$ROOT/build/$name"
}

build_cmake ogg-1.3.5
build_cmake vorbis-1.3.7
build_cmake opus-1.5.2 -DOPUS_BUILD_TESTING=OFF -DOPUS_BUILD_PROGRAMS=OFF \
    -DOPUS_INSTALL_PKG_CONFIG_MODULE=ON -DOPUS_DRED=OFF -DOPUS_OSCE=OFF

cd "$ROOT/src/lame-3.100"
if [ ! -f Makefile ]; then
    sh ./configure --prefix="$PREFIX" --build=x86_64-w64-mingw32 --host=x86_64-w64-mingw32 \
        --disable-shared --enable-static --disable-frontend --disable-decoder \
        --disable-cpml --disable-nasm > "$ROOT/logs/lame-configure.log" 2>&1
fi
make -j"$JOBS" > "$ROOT/logs/lame-build.log" 2>&1
make install > "$ROOT/logs/lame-install.log" 2>&1

mkdir -p "$ROOT/build/ffmpeg"
cd "$ROOT/build/ffmpeg"
if [ ! -f config.h ]; then
    sh "$ROOT/src/ffmpeg-7.1.3/configure" \
        --prefix="$ROOT/output" --target-os=mingw32 --arch=x86_64 \
        --disable-gpl --disable-nonfree --disable-version3 --disable-autodetect \
        --disable-shared --enable-static --enable-schannel --disable-debug --disable-doc \
        --disable-x86asm --disable-programs --enable-ffmpeg --enable-ffprobe \
        --disable-encoders \
        --enable-encoder=aac,flac,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,libmp3lame,libopus,libvorbis,png,mjpeg \
        --enable-libmp3lame --enable-libopus --enable-libvorbis \
        --pkg-config-flags=--static --extra-cflags="-I$PREFIX/include" \
        --extra-ldflags="-L$PREFIX/lib -static" \
        > "$ROOT/logs/ffmpeg-configure.log" 2>&1
fi
make -j"$JOBS" > "$ROOT/logs/ffmpeg-build.log" 2>&1
make install > "$ROOT/logs/ffmpeg-install.log" 2>&1
"$ROOT/output/bin/ffmpeg.exe" -version > "$ROOT/output/version.txt" 2>&1
"$ROOT/output/bin/ffmpeg.exe" -L > "$ROOT/output/license.txt" 2>&1
printf 'Decoder build complete: %s\n' "$ROOT/output/bin/ffmpeg.exe"
