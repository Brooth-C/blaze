"""Stage the pinned native SCNet package from a local release ZIP, without downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.native_scnet import ARCHIVE_SHA, verified_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != ARCHIVE_SHA:
            parser.error('Native SCNet archive checksum mismatch.')
    if args.output.exists():
        parser.error('Choose a new output directory.')
    args.output.mkdir(parents=True)
    try:
        files = {}
        with zipfile.ZipFile(args.archive) as archive:
            if sum(row.file_size for row in archive.infolist()) > 128*1024**2:
                raise ValueError('Candidate archive exceeds its bound.')
            for row in archive.infolist():
                relative = Path(row.filename)
                if (relative.is_absolute() or '..' in relative.parts or '\\' in row.filename
                        or not relative.parts or relative.parts[0] != 'scnet_coreml.mlpackage'
                        or (row.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('Invalid candidate archive path.')
                if row.is_dir():
                    continue
                path = args.output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(row) as source, path.open('xb') as target:
                    shutil.copyfileobj(source, target)
                files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {'schema_version':1,'candidate':'native-scnet-fp16','experimental':True,
                    'archive_sha256':ARCHIVE_SHA,'files':files,'precision':'fp16',
                    'source':'https://github.com/demixr/scnet-executorch/releases/tag/v0.1.2'}
        (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        verified_package(args.output)
    except BaseException:
        shutil.rmtree(args.output)
        raise
    print(args.output)


if __name__ == '__main__':
    main()
