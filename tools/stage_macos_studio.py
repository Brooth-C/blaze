"""Stage unchanged reviewed models and pinned native macOS downloader tools."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = 'https://github.com/Brooth-C/blaze/releases/download/windows-v0.6.0/Blaze-Windows.zip'
MODEL_SHA = '73bfa1bc0ce0657bb2792b5552c6614844fee3ebbea3bdccfa64ed4c659f96dc'
NODE_SHA = {
    'arm64': 'cc04a76a09f79290194c0646f48fec40354d88969bec467789a5d55dd097f949',
    'x86_64': '00df9c5df3e4ec6848c26b70fb47bf96492f342f4bed6b17f12d99b3a45eeecc',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, path, checksum=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or (checksum and digest(path) != checksum):
        request = urllib.request.Request(url, headers={'User-Agent': 'Blaze-Mac-build/0.6.0'})
        temporary = path.with_suffix(path.suffix + '.part')
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        if checksum and digest(temporary) != checksum:
            temporary.unlink()
            raise ValueError('Checksum mismatch: ' + path.name)
        temporary.replace(path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--arch', choices=NODE_SHA, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    models_zip = fetch(MODEL_URL, work / 'models.zip', MODEL_SHA)
    model_root = ROOT / 'music_studio/models'
    model_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(models_zip) as archive:
        prefix = 'Blaze/_internal/music_studio/models/'
        for member in archive.namelist():
            if member.startswith(prefix) and not member.endswith('/'):
                name = member.removeprefix(prefix)
                if Path(name).name != name:
                    raise ValueError('Invalid model asset path')
                (model_root / name).write_bytes(archive.read(member))
    tools = work / 'bin'
    tools.mkdir(parents=True, exist_ok=True)
    node_arch = 'x64' if args.arch == 'x86_64' else 'arm64'
    prefix = f'node-v22.20.0-darwin-{node_arch}'
    node_archive = fetch(f'https://nodejs.org/dist/v22.20.0/{prefix}.tar.gz', work / (prefix + '.tar.gz'), NODE_SHA[args.arch])
    notices = work / 'notices'
    notices.mkdir(parents=True, exist_ok=True)
    with tarfile.open(node_archive) as archive:
        for member, target in ((prefix + '/bin/node', tools / 'node'), (prefix + '/LICENSE', notices / 'Node-LICENSE.txt')):
            with archive.extractfile(member) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
    for name in ('LICENSE', 'THIRD_PARTY_LICENSES.txt'):
        fetch(f'https://raw.githubusercontent.com/yt-dlp/yt-dlp/2026.08.19/{name}', notices / ('yt-dlp-' + name))
    fetch('https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE', notices / 'Python-LICENSE.txt')
    (notices / 'SOURCE-LINKS.txt').write_text(
        'Node 22.20.0 is the unchanged official binary; yt-dlp is built from plain PyPI 2026.8.19 with EJS 0.8.0.\n'
        'Node source: https://nodejs.org/dist/v22.20.0/node-v22.20.0.tar.gz\n'
        'yt-dlp source: https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.tar.gz\n'
        'Bundled third-party sources and notices: yt-dlp-THIRD_PARTY_LICENSES.txt.\n'
        'Optional GPL libraries are excluded from the separate downloader. Each tool remains independently replaceable.\n', encoding='utf-8')
    for path in tools.iterdir():
        path.chmod(0o755)
    (work / 'tool-manifest.json').write_text(json.dumps({
        'models_sha256': MODEL_SHA, 'node_archive_sha256': NODE_SHA[args.arch],
        'architecture': args.arch,
        'tools': {p.name: digest(p) for p in tools.iterdir()},
    }, indent=2), encoding='utf-8')
    print('Verified original models and native Mac tools staged.')


if __name__ == '__main__':
    main()
