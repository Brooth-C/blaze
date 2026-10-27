"""Fetch only the original checksum/size-pinned BS-RoFormer checkpoint."""
from pathlib import Path
import argparse
import hashlib
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.roformer_assets import CHECKPOINT_SHA


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.part')
    url = 'https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/model_bs_roformer_ep_17_sdr_9.6568.ckpt'
    try:
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open('wb') as target:
            count = 0
            while block := source.read(1024 * 1024):
                count += len(block)
                if count > 527385512:
                    raise ValueError('Checkpoint exceeds its reviewed size.')
                target.write(block)
        with temporary.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if count != 527385512 or checksum != CHECKPOINT_SHA:
            raise ValueError('Original checkpoint checksum or size mismatch.')
        temporary.replace(args.output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
