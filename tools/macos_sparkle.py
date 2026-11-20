"""Stage the pinned upstream Sparkle distribution, preserving framework symlinks."""
import argparse
import hashlib
from pathlib import Path
import tarfile
import urllib.request

VERSION = '2.10.1'
SHA256 = '1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27'
URL = f'https://github.com/sparkle-project/Sparkle/releases/download/{VERSION}/Sparkle-{VERSION}.tar.xz'


def stage(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'Sparkle.tar.xz'
    if not archive.exists():
        urllib.request.urlretrieve(URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError('Sparkle archive checksum mismatch.')
    with tarfile.open(archive) as source:
        members = [m for m in source.getmembers()
                   if m.name.removeprefix('./') == 'LICENSE'
                   or m.name.removeprefix('./').startswith(('Sparkle.framework/', 'bin/'))]
        source.extractall(destination, members=members, filter='data')
    if not (destination / 'Sparkle.framework/Versions/B/Sparkle').is_file():
        raise ValueError('Incomplete Sparkle framework.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    stage(parser.parse_args().output)
