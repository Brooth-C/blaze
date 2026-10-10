#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [[ -z "${TERMUX_VERSION:-}" || -z "${PREFIX:-}" ]] || ! command -v pkg >/dev/null; then
    printf 'Run this installer inside Termux on Android.\n' >&2
    exit 1
fi
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$SOURCE/blaze.py" ]] || { printf 'Extract the entire Blaze ZIP first.\n' >&2; exit 1; }
ROOT="$HOME/Blaze"
mkdir -p "$ROOT/.runtime"
LOCK="$ROOT/.runtime/termux-setup.lock"
mkdir "$LOCK" 2>/dev/null || { printf 'Another setup is running.\n' >&2; exit 1; }
STAGING=""
cleanup() {
    [[ -z "$STAGING" ]] || rm -rf -- "$STAGING"
    rmdir "$LOCK"
}
trap cleanup EXIT
printf 'Installing Blaze for Android / Termux in %s\n' "$ROOT"
# Android executables must come from Termux, not desktop Linux archives.
pkg install -y python ffmpeg aria2
python -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
STAGING="$(mktemp -d "$ROOT/.runtime/termux-setup.XXXXXX")"
python -m py_compile "$SOURCE/blaze.py"
if [[ ! -x "$ROOT/.runtime/venv/bin/python" ]]; then
    python -m venv "$ROOT/.runtime/venv"
fi
PYTHON="$ROOT/.runtime/venv/bin/python"
"$PYTHON" -m pip install --upgrade yt-dlp rich mutagen
"$PYTHON" -c 'import yt_dlp, rich, mutagen'
ffmpeg -version >/dev/null
aria2c --version >/dev/null
cp "$SOURCE/blaze.py" "$STAGING/blaze.py"
"$PYTHON" "$STAGING/blaze.py" --version
cat > "$STAGING/Start-Blaze.sh" <<'LAUNCHER'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$ROOT/.runtime/venv/bin:${PREFIX:?}/bin:$PATH"
exec "$ROOT/.runtime/venv/bin/python" "$ROOT/App/blaze.py" "$@"
LAUNCHER
chmod 755 "$STAGING/Start-Blaze.sh"
mkdir -p "$ROOT/App" "$ROOT/Config" "$ROOT/Audio" "$ROOT/Video" "$ROOT/Reports"
mv -f "$STAGING/blaze.py" "$ROOT/App/blaze.py"
mv -f "$STAGING/Start-Blaze.sh" "$ROOT/Start-Blaze.sh"
cp "$SOURCE/LICENSE.txt" "$SOURCE/THIRD-PARTY-NOTICES.md" "$ROOT/"
printf '\nReady. Start with: bash ~/Blaze/Start-Blaze.sh\n'
