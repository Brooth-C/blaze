#!/bin/bash
set -euo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/Blaze"
RUNTIME="$ROOT/.runtime"
BIN="$RUNTIME/bin"
mkdir -p "$BIN" "$RUNTIME/tmp"
STAGING="$(mktemp -d "$RUNTIME/setup.XXXXXX")"
finish() {
    result=$?
    rm -rf "$STAGING"
    if [ "$result" -eq 0 ]; then
        printf '\nInstalled. Double-click ~/Blaze/Start-Blaze.command\n'
    else
        printf '\nInstallation failed. Read the error above and rerun the installer.\n'
    fi
    read -r -p 'Press Enter to close...' unused || true
}
trap finish EXIT
export UV_PYTHON_INSTALL_DIR="$RUNTIME/python"
export UV_PYTHON_BIN_DIR="$BIN"
export UV_TOOL_DIR="$RUNTIME/tools"
export UV_TOOL_BIN_DIR="$BIN"
export UV_CACHE_DIR="$RUNTIME/cache"
export UV_NO_CONFIG=1
export UV_PYTHON_INSTALL_BIN=0
export TMPDIR="$RUNTIME/tmp"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME || true
case "$(uname -m)" in
    arm64) TARGET='aarch64-apple-darwin' ;;
    x86_64) TARGET='x86_64-apple-darwin' ;;
    *) printf 'Unsupported Mac architecture.\n'; exit 1 ;;
esac
VERSION='0.12.19'
ASSET="uv-$TARGET.tar.gz"
URL="https://github.com/astral-sh/uv/releases/download/$VERSION"
printf '\nBLAZE PRIVATE INSTALLER\nDestination: %s\n' "$ROOT"
printf '\n[1/5] Downloading private runtime manager...\n'
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 30 --max-time 300 "$URL/$ASSET" -o "$STAGING/$ASSET"
curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 30 --max-time 120 "$URL/$ASSET.sha256" -o "$STAGING/checksum"
EXPECTED="$(awk 'NR==1 {print $1}' "$STAGING/checksum")"
ACTUAL="$(shasum -a 256 "$STAGING/$ASSET" | awk '{print $1}')"
if [ "${#EXPECTED}" -ne 64 ] || [ "$EXPECTED" != "$ACTUAL" ]; then
    printf 'uv checksum mismatch. Nothing from this download was executed.\n'
    exit 1
fi
tar -xzf "$STAGING/$ASSET" -C "$STAGING"
UV_SOURCE="$STAGING/uv-$TARGET/uv"
[ -f "$UV_SOURCE" ] || { printf 'Unexpected uv archive contents.\n'; exit 1; }
cp "$UV_SOURCE" "$BIN/uv"
chmod 755 "$BIN/uv"
UV="$BIN/uv"
"$UV" --version
printf '\n[2/5] Installing private Python 3.13...\n'
"$UV" python install 3.13 --no-bin --no-config
printf '\n[3/5] Preparing private environment...\n'
PYTHON="$RUNTIME/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    "$UV" venv --python 3.13 --managed-python --seed --no-config "$RUNTIME/venv"
fi
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10); print(sys.version)'
printf '\n[4/5] Installing Blaze dependencies...\n'
"$UV" pip install --python "$PYTHON" --no-config --no-cache yt-dlp rich mutagen imageio-ffmpeg
FFMPEG="$("$PYTHON" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
cp "$FFMPEG" "$BIN/ffmpeg"
chmod 755 "$BIN/ffmpeg"
"$BIN/ffmpeg" -version
printf '\n[5/5] Installing Blaze and launcher...\n'
mkdir -p "$ROOT/App"
cp "$BASE/Blaze-Universal-4.1.20.py" "$ROOT/App/Blaze-Universal-4.1.20.py"
"$PYTHON" -m py_compile "$ROOT/App/Blaze-Universal-4.1.20.py"
cat > "$ROOT/Start-Blaze.command" <<'LAUNCH'
#!/bin/bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="$ROOT/.runtime/bin:$ROOT/.runtime/venv/bin:$PATH"
export TMPDIR="$ROOT/.runtime/tmp"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME || true
"$ROOT/.runtime/venv/bin/python" "$ROOT/App/Blaze-Universal-4.1.20.py" "$@"
result=$?
if [ "$result" -ne 0 ]; then read -r -p 'Press Enter to close...' unused || true; fi
exit "$result"
LAUNCH
chmod 755 "$ROOT/Start-Blaze.command"
"$PYTHON" "$ROOT/App/Blaze-Universal-4.1.20.py" --help
