#!/bin/sh
# Native, unmodified LGPL decoder build. This does not use a Homebrew FFmpeg.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Darwin ]; then
    printf 'This recipe must run natively on macOS.\n' >&2
    exit 1
fi
NATIVE_ARCH=$(uname -m)
case "$NATIVE_ARCH" in
    arm64) FFMPEG_ARCH=aarch64 ;;
    x86_64) FFMPEG_ARCH=x86_64 ;;
    *) printf 'Unsupported Mac architecture: %s\n' "$NATIVE_ARCH" >&2; exit 1 ;;
esac
JOBS=${BLAZE_CODEC_JOBS:-4}
case "$JOBS" in
    ''|*[!0-9]*|0) printf 'BLAZE_CODEC_JOBS must be a positive integer.\n' >&2; exit 1 ;;
esac
export MACOSX_DEPLOYMENT_TARGET=13.0
SDKROOT=$(xcrun --sdk macosx --show-sdk-path)
export SDKROOT
export CC="$(xcrun --sdk macosx --find clang)"
export CXX="$(xcrun --sdk macosx --find clang++)"
export AR="$(xcrun --sdk macosx --find ar)"
export RANLIB="$(xcrun --sdk macosx --find ranlib)"
export NM="$(xcrun --sdk macosx --find nm)"
export STRIP="$(xcrun --sdk macosx --find strip)"
# Ignore caller library paths and compiler options. No -march=native or cached
# build products: binaries must also work on other Macs of this architecture.
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH DYLD_LIBRARY_PATH
unset CMAKE_PREFIX_PATH CMAKE_LIBRARY_PATH CMAKE_INCLUDE_PATH LDFLAGS CPPFLAGS
export CFLAGS="-O2 -arch $NATIVE_ARCH -isysroot $SDKROOT -mmacosx-version-min=13.0"
export CXXFLAGS="$CFLAGS"
mkdir -p "$ROOT/logs" "$ROOT/output/bin"
WORK=$(mktemp -d "$ROOT/build.XXXXXX")
PREFIX="$WORK/prefix"
mkdir -p "$PREFIX"
export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR=

cleanup() {
    # WORK is created above by mktemp inside this recipe's own directory.
    case "$WORK" in "$ROOT"/build.*) rm -rf -- "$WORK" ;; esac
}
trap cleanup EXIT HUP INT TERM

build_cmake() {
    name=$1
    shift
    cmake -S "$ROOT/src/$name" -B "$WORK/$name" -G 'Unix Makefiles' \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCMAKE_MAKE_PROGRAM=/usr/bin/make \
        -DCMAKE_PREFIX_PATH="$PREFIX" -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
        -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX" \
        -DCMAKE_OSX_ARCHITECTURES="$NATIVE_ARCH" \
        -DCMAKE_OSX_SYSROOT="$SDKROOT" -DCMAKE_OSX_DEPLOYMENT_TARGET=13.0 \
        -DCMAKE_IGNORE_PREFIX_PATH='/opt/homebrew;/usr/local' \
        -DCMAKE_FIND_USE_CMAKE_ENVIRONMENT_PATH=OFF \
        -DCMAKE_FIND_USE_SYSTEM_ENVIRONMENT_PATH=OFF \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
        -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF \
        "$@" > "$ROOT/logs/$name-configure.log" 2>&1
    cmake --build "$WORK/$name" --parallel "$JOBS" > "$ROOT/logs/$name-build.log" 2>&1
    cmake --install "$WORK/$name" > "$ROOT/logs/$name-install.log" 2>&1
}

build_cmake ogg-1.3.5
build_cmake vorbis-1.3.7
build_cmake opus-1.5.2 -DOPUS_BUILD_TESTING=OFF -DOPUS_BUILD_PROGRAMS=OFF \
    -DOPUS_INSTALL_PKG_CONFIG_MODULE=ON -DOPUS_DRED=OFF -DOPUS_OSCE=OFF

mkdir -p "$WORK/lame"
cd "$WORK/lame"
NATIVE_TRIPLE="$FFMPEG_ARCH-apple-darwin$(uname -r)"
sh "$ROOT/src/lame-3.100/configure" --prefix="$PREFIX" \
    --build="$NATIVE_TRIPLE" --host="$NATIVE_TRIPLE" \
    --disable-shared --enable-static --disable-frontend --disable-decoder \
    --disable-cpml --disable-nasm > "$ROOT/logs/lame-configure.log" 2>&1
make -j"$JOBS" > "$ROOT/logs/lame-build.log" 2>&1
make install > "$ROOT/logs/lame-install.log" 2>&1

mkdir -p "$WORK/ffmpeg"
cd "$WORK/ffmpeg"
sh "$ROOT/src/ffmpeg-7.1.3/configure" \
    --prefix="$ROOT/output" --target-os=darwin --arch="$FFMPEG_ARCH" \
    --cc="$CC" --cxx="$CXX" --ar="$AR" --ranlib="$RANLIB" --nm="$NM" \
    --disable-gpl --disable-nonfree --disable-version3 --disable-autodetect \
    --disable-shared --enable-static --enable-securetransport --enable-zlib \
    --disable-debug --disable-doc --disable-x86asm \
    --disable-programs --enable-ffmpeg --enable-ffprobe \
    --disable-encoders \
    --enable-encoder=aac,flac,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,libmp3lame,libopus,libvorbis,png,mjpeg \
    --enable-libmp3lame --enable-libopus --enable-libvorbis \
    --pkg-config-flags=--static --extra-cflags="$CFLAGS -I$PREFIX/include" \
    --extra-ldflags="-arch $NATIVE_ARCH -isysroot $SDKROOT -mmacosx-version-min=13.0 -L$PREFIX/lib" \
    > "$ROOT/logs/ffmpeg-configure.log" 2>&1
make -j"$JOBS" > "$ROOT/logs/ffmpeg-build.log" 2>&1
make install > "$ROOT/logs/ffmpeg-install.log" 2>&1
cp ffbuild/config.mak "$ROOT/output/config.mak"
cp ffbuild/config.log "$ROOT/output/config.log"
"$ROOT/output/bin/ffmpeg" -version > "$ROOT/output/version.txt" 2>&1
"$ROOT/output/bin/ffmpeg" -buildconf > "$ROOT/output/buildconf.txt" 2>&1
"$ROOT/output/bin/ffmpeg" -L > "$ROOT/output/license.txt" 2>&1
"$ROOT/output/bin/ffprobe" -version > "$ROOT/output/probe-version.txt" 2>&1
{
    printf 'Native architecture: %s\n' "$NATIVE_ARCH"
    printf 'Deployment target: %s\n' "$MACOSX_DEPLOYMENT_TARGET"
    sw_vers
    xcodebuild -version || true
    "$CC" --version
    cmake --version
    pkg-config --version
} > "$ROOT/output/toolchain.txt" 2>&1
# Reject dynamically linked codec libraries and all accidental Homebrew paths.
for program in ffmpeg ffprobe; do
    otool -L "$ROOT/output/bin/$program" > "$ROOT/output/$program-dependencies.txt"
    awk 'NR > 1 {print $1}' "$ROOT/output/$program-dependencies.txt" | while IFS= read -r dep; do
        case "$dep" in
            /usr/lib/*|/System/Library/*) ;;
            *) printf 'Unexpected external decoder dependency: %s\n' "$dep" >&2; exit 1 ;;
        esac
    done
    file "$ROOT/output/bin/$program"
done
python3 "$ROOT/package_sources.py"
printf 'Decoder build complete: %s (%s)\n' "$ROOT/output/bin/ffmpeg" "$NATIVE_ARCH"
