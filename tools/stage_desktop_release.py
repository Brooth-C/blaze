"""Reuse checksum-verified, unchanged decoder/model assets from the prior release."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = '73bfa1bc0ce0657bb2792b5552c6614844fee3ebbea3bdccfa64ed4c659f96dc'
NODE_SHA = '00bbd05e306ea68b6e13e17360d0e2f680b493ef95f2fea1c4296ff7437530bc'


def fetch(url, path, checksum):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum:
        return path
    temporary = path.with_suffix('.part')
    with urllib.request.urlopen(url, timeout=180) as response, temporary.open('wb') as output:
        shutil.copyfileobj(response, output, 1024 * 1024)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
        temporary.unlink()
        raise ValueError('Release checksum mismatch: ' + path.name)
    temporary.replace(path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=('windows', 'linux'), required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    archive_path = fetch('https://github.com/Brooth-C/blaze/releases/download/windows-v0.6.0/Blaze-Windows.zip', work / 'windows-models.zip', MODEL_SHA)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.namelist():
            prefix = 'Blaze/_internal/music_studio/models/'
            if member.startswith(prefix) and not member.endswith('/'):
                name = member.removeprefix(prefix)
                if Path(name).name != name:
                    raise ValueError('Invalid model path')
                target = ROOT / 'music_studio/models' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
            if args.platform == 'windows' and not member.endswith('/'):
                for prefix, destination in [('Blaze/_internal/bin/', work / 'bin'), ('Blaze/licenses/', work / 'licenses')]:
                    if member.startswith(prefix):
                        relative = Path(member.removeprefix(prefix))
                        if '..' in relative.parts:
                            raise ValueError('Invalid archived path')
                        target = destination / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(member))
    if args.platform == 'windows':
        materials = work / 'decoder'
        materials.mkdir(exist_ok=True)
        for name in ('decoder-manifest.json', 'FFmpeg-LGPL-Corresponding-Sources.zip'):
            shutil.copy2(work / 'licenses' / name, materials / name)
        shutil.copytree(work / 'licenses/FFmpeg', materials / 'licenses', dirs_exist_ok=True)
        manifest = json.loads((materials / 'decoder-manifest.json').read_text())
        if hashlib.sha256((work / 'bin/ffmpeg.exe').read_bytes()).hexdigest() != manifest['binary']['sha256']:
            raise ValueError('Decoder differs from its corresponding-source manifest')
    else:
        node = fetch('https://nodejs.org/dist/v22.20.0/node-v22.20.0-linux-x64.tar.xz', work / 'node.tar.xz', NODE_SHA)
        (work / 'bin').mkdir(exist_ok=True)
        (work / 'notices').mkdir(exist_ok=True)
        with tarfile.open(node) as archive:
            for member, target in [('node-v22.20.0-linux-x64/bin/node', work / 'bin/node'), ('node-v22.20.0-linux-x64/LICENSE', work / 'notices/Node-LICENSE.txt')]:
                with archive.extractfile(member) as stream, target.open('wb') as output:
                    shutil.copyfileobj(stream, output)
        (work / 'bin/node').chmod(0o755)
    print('Verified desktop assets staged for', args.platform)


if __name__ == '__main__':
    main()
