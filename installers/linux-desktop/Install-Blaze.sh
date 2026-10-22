#!/bin/sh
# Install the desktop app into the current user's account; no sudo or system edits.
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DESTINATION=${BLAZE_INSTALL_DIR:-"$HOME/.local/share/BlazeApp"}
case "$(uname -m)" in x86_64|amd64) ;; *) echo 'This package requires Linux x86_64.' >&2; exit 1;; esac
PYTHON=${BLAZE_PYTHON:-/usr/bin/python3}
command -v "$PYTHON" >/dev/null
command -v ffmpeg >/dev/null || { echo 'Install FFmpeg first: sudo apt install ffmpeg' >&2; exit 1; }
"$PYTHON" -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk; gi.require_version("WebKit2", "4.1"); from gi.repository import WebKit2' || {
    echo 'Install the renderer first: sudo apt install python3-venv python3-gi python3-gi-cairo gir1.2-webkit2-4.1 gstreamer1.0-libav gstreamer1.0-plugins-good ffmpeg' >&2
    exit 1
}
mkdir -p "$DESTINATION"
cp -R "$SOURCE/music_studio" "$SOURCE/bin" "$SOURCE/licenses" "$DESTINATION/"
cp "$SOURCE/blaze.py" "$SOURCE/requirements.txt" "$SOURCE/LICENSE.txt" "$SOURCE/THIRD-PARTY-NOTICES.md" "$SOURCE/blaze-logo.png" "$DESTINATION/"
"$PYTHON" -m venv --system-site-packages "$DESTINATION/.venv"
"$DESTINATION/.venv/bin/python" -m pip install -r "$DESTINATION/requirements.txt"
ln -sf "$(command -v ffmpeg)" "$DESTINATION/bin/ffmpeg"
if command -v ffprobe >/dev/null; then ln -sf "$(command -v ffprobe)" "$DESTINATION/bin/ffprobe"; fi
ln -sf "$DESTINATION/.venv/bin/yt-dlp" "$DESTINATION/bin/yt-dlp"
cat > "$DESTINATION/Blaze" <<'LAUNCH'
#!/bin/sh
set -eu
APP=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP"
exec "$APP/.venv/bin/python" -m music_studio.linux_app "$@"
LAUNCH
chmod +x "$DESTINATION/Blaze" "$DESTINATION/bin/node"
"$DESTINATION/.venv/bin/python" - "$DESTINATION" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'
entry = Path.home() / '.local/share/applications/blaze.desktop'
entry.parent.mkdir(parents=True, exist_ok=True)
entry.write_text('[Desktop Entry]\nType=Application\nName=Blaze\nComment=Downloads and offline Music Studio\nExec=' + quote(root / 'Blaze') + '\nIcon=' + str(root / 'blaze-logo.png') + '\nTerminal=false\nCategories=AudioVideo;Utility;\n', encoding='utf-8')
PY
printf 'Blaze installed. Open it from your applications menu or run: %s/Blaze\n' "$DESTINATION"
