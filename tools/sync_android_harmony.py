"""Stage exact shared NumPy harmony source for Android; no model downloads."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'music_studio'
TARGET = ROOT / 'android/app/src/main/python/blaze_studio_shared'


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / '__init__.py').write_text('"""Exact shared Blaze chord frontend and decoder."""\n', encoding='utf-8')
    hashes = {}
    for name in ('chords.py', 'evidence.py', 'lv_frontend.py', 'structured.py'):
        shutil.copyfile(SOURCE / name, TARGET / name)
        hashes[name] = hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
    (TARGET / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(hashes))


if __name__ == '__main__':
    main()
