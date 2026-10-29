"""Download the size/hash-pinned original Mega 53 weights, build time only."""
from pathlib import Path
import argparse
import hashlib
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.instrument_assets import CHECKPOINT_BYTES, CHECKPOINT_SHA, CHECKPOINT_URL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.part')
    try:
        with urllib.request.urlopen(CHECKPOINT_URL, timeout=120) as source, temporary.open('wb') as target:
            count = 0
            while block := source.read(1048576):
                count += len(block)
                if count > CHECKPOINT_BYTES:
                    raise ValueError('Mega checkpoint exceeds its reviewed size.')
                target.write(block)
        with temporary.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if count != CHECKPOINT_BYTES or checksum != CHECKPOINT_SHA:
            raise ValueError('Original Mega checkpoint checksum or size mismatch.')
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
