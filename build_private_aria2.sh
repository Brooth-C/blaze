#!/bin/bash
# Build on GitHub's Mac runners; users only download the resulting executable.
set -euo pipefail
[ "$(uname -s)" = Darwin ] || { printf 'This build requires a Mac runner.\n'; exit 1; }
BUILD_ROOT="${RUNNER_TEMP:?}/blaze-aria2-build"
mkdir -p "$BUILD_ROOT/assets"
cd "$BUILD_ROOT"
SOURCE='aria2-1.37.0.tar.xz'
SOURCE_SHA='60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b'
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 30 --max-time 180 \
    "https://github.com/aria2/aria2/releases/download/release-1.37.0/$SOURCE" -o "$SOURCE"
[ "$(shasum -a 256 "$SOURCE" | awk '{print $1}')" = "$SOURCE_SHA" ] || { printf 'Source checksum mismatch.\n'; exit 1; }
tar -xf "$SOURCE"
SDK="$(xcrun --show-sdk-path)"
export CC="$(xcrun -f clang)" CXX="$(xcrun -f clang++)"
export MACOSX_DEPLOYMENT_TARGET=11.0
export CFLAGS="-Os -isysroot $SDK -mmacosx-version-min=11.0"
export CXXFLAGS="$CFLAGS -std=c++11"
export CPPFLAGS="-I$SDK/usr/include/libxml2"
export LDFLAGS="-isysroot $SDK -L$SDK/usr/lib -mmacosx-version-min=11.0"
# Supply the SDK libraries explicitly. Do not discover Homebrew packages.
export PKG_CONFIG=/usr/bin/false
export LIBXML2_CFLAGS="-I$SDK/usr/include/libxml2" LIBXML2_LIBS='-lxml2'
export SQLITE3_CFLAGS="-I$SDK/usr/include" SQLITE3_LIBS='-lsqlite3'
export ZLIB_CFLAGS="-I$SDK/usr/include" ZLIB_LIBS='-lz'
cd aria2-1.37.0
./configure --with-appletls --without-openssl --without-gnutls \
    --without-libnettle --without-libgcrypt --without-libgmp \
    --without-libssh2 --without-libcares --without-libuv --without-libexpat \
    --with-libxml2 --with-sqlite3 --with-libz --disable-nls
make -j"$(sysctl -n hw.logicalcpu)"
case "$(uname -m)" in
    arm64) ARCH=arm64 ;;
    x86_64) ARCH=x64 ;;
    *) exit 1 ;;
esac
DEST="$BUILD_ROOT/assets/aria2c-1.37.0-macos-$ARCH"
cp src/aria2c "$DEST"
strip "$DEST"
codesign --force --sign - "$DEST"
"$DEST" --version | tee "$BUILD_ROOT/version.txt"
grep -F 'aria2 version 1.37.0' "$BUILD_ROOT/version.txt"
grep -F 'AppleTLS' "$BUILD_ROOT/version.txt"
grep -F 'HTTPS' "$BUILD_ROOT/version.txt"
while IFS= read -r library; do
    case "$library" in
        /usr/lib/*|/System/Library/Frameworks/*) ;;
        *) printf 'Non-system dependency: %s\n' "$library"; exit 1 ;;
    esac
done < <(otool -L "$DEST" | awk 'NR>1 {print $1}')
# Exercise TLS and the macOS trust store, not just --version.
"$DEST" --no-conf=true --enable-rpc=false --max-tries=1 --connect-timeout=30 \
    --timeout=30 --dir="$BUILD_ROOT" --out=download-check.html https://aria2.github.io/
test -s "$BUILD_ROOT/download-check.html"
cp COPYING "$BUILD_ROOT/assets/aria2-COPYING.txt"
cp "$BUILD_ROOT/$SOURCE" "$BUILD_ROOT/assets/$SOURCE"
cd "$BUILD_ROOT/assets"
shasum -a 256 "$(basename "$DEST")" > "$(basename "$DEST").sha256"
