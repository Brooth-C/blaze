"""Stage reviewed chord/stem models and pinned native macOS downloader tools."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODEL_URL = 'https://github.com/Brooth-C/blaze/releases/download/windows-v0.6.0/Blaze-Windows.zip'
MODEL_SHA = '73bfa1bc0ce0657bb2792b5552c6614844fee3ebbea3bdccfa64ed4c659f96dc'
NODE_SHA = {
    'arm64': 'cc04a76a09f79290194c0646f48fec40354d88969bec467789a5d55dd097f949',
}
STEM_MODEL = {
    'file': 'scnet_cpu.onnx', 'bytes': 52271228,
    'sha256': 'f2c050b7264d2b2401497beb712c26a50e6162dfb951041060f23f84929d600e',
    'url': 'https://github.com/demixr/scnet-executorch/releases/download/v0.1.2/scnet_cpu.onnx',
}
STEM_LICENSES = {
    'LICENSE-SCNet.txt': {
        'url': 'https://raw.githubusercontent.com/starrytong/SCNet/5d95bf96b19c3eede63248d171efeca8e3abb948/LICENSE',
        'sha256': '0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513',
    },
    'LICENSE-SCNet-Export.txt': {
        'url': 'https://raw.githubusercontent.com/demixr/scnet-executorch/fae523107add29547b68be1730951524bdad6a2b/LICENSE',
        'sha256': '2ce46aa4a66b514b6ce41d7a0da0b87d1ac8a750f14fef014c0a98431446f4d7',
    },
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


def stage_stems(cache, target):
    """Stage one bounded, checksum-pinned model and both upstream notices."""
    target.mkdir(parents=True, exist_ok=True)
    sources = {STEM_MODEL['file']: STEM_MODEL, **STEM_LICENSES}
    for name, metadata in sources.items():
        destination = cache / name
        size = metadata.get('bytes')
        limit = size or 65536
        if not destination.is_file() or digest(destination) != metadata['sha256']:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.part')
            try:
                request = urllib.request.Request(metadata['url'], headers={'User-Agent': 'Blaze-Mac-build/0.10.0'})
                with urllib.request.urlopen(request, timeout=120) as response, temporary.open('wb') as output:
                    count = 0
                    while block := response.read(1024 * 1024):
                        count += len(block)
                        if count > limit:
                            raise ValueError('Stem asset exceeds its pinned bound: ' + name)
                        output.write(block)
                if (size is not None and count != size) or digest(temporary) != metadata['sha256']:
                    raise ValueError('Stem asset checksum or size mismatch: ' + name)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        if size is not None and destination.stat().st_size != size:
            raise ValueError('Stem model size mismatch.')
        shutil.copy2(destination, target / name)
    manifest = {
        'name': 'SCNet', 'version': 'demixr-v0.1.2', 'license': 'MIT',
        'model': {key: STEM_MODEL[key] for key in ('file', 'bytes', 'sha256')},
        'sample_rate': 44100, 'segment_samples': 343980,
        'stems': ['drums', 'bass', 'other', 'vocals'],
        'licenses': {name: {'file': name, **metadata} for name, metadata in STEM_LICENSES.items()},
        'source': {
            'model_url': STEM_MODEL['url'],
            'author_repository': 'https://github.com/starrytong/SCNet/tree/5d95bf96b19c3eede63248d171efeca8e3abb948',
            'export_repository': 'https://github.com/demixr/scnet-executorch/tree/fae523107add29547b68be1730951524bdad6a2b',
            'original_checkpoint': {
                'author_readme_download_id': '1CdEIIqsoRfHn1SJ7rccPfyYioW3BlXcW',
                'bytes': 42434545,
                'sha256': 'f8aff3bc8dd816aad392800d9d69519add719a2fbd22550af6f8cb2138d25ff5',
            },
            'description': 'Official SCNet checkpoint, exported as an ONNX spectral core by Demixr. Original model and export notices are retained.',
        },
    }
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def stage_piano(cache, target):
    from music_studio.piano_assets import MODELS, LICENSES
    target.mkdir(parents=True, exist_ok=True)
    assets = {meta['file']: meta for meta in MODELS.values()}
    assets.update(LICENSES)
    for name, meta in assets.items():
        destination = cache / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.is_file() or digest(destination) != meta['sha256']:
            temporary = destination.with_suffix('.part')
            try:
                with urllib.request.urlopen(meta['url'], timeout=120) as source, temporary.open('wb') as output:
                    count = 0
                    while block := source.read(1024 * 1024):
                        count += len(block)
                        if count > meta['bytes']:
                            raise ValueError('Piano asset exceeds its pinned size.')
                        output.write(block)
                if count != meta['bytes'] or digest(temporary) != meta['sha256']:
                    raise ValueError('Piano asset checksum mismatch.')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        if destination.stat().st_size != meta['bytes']:
            raise ValueError('Piano asset size mismatch.')
        shutil.copy2(destination, target / name)
    manifest = {'model': 'Spleeter 5stems', 'outputs': ['piano', 'accompaniment'],
                'five_outputs': ['vocals', 'drums', 'bass', 'piano', 'other'],
                'sample_rate': 44100, 'models': MODELS, 'licenses': LICENSES,
                'weight_license': 'MIT',
                'license_evidence': 'https://doi.org/10.21105/joss.02154',
                'export_source': 'https://github.com/matthewbae/spleeter-onnx-models/tree/1215fccebccf416ecd02fa7e08ed74413b15015f',
                'official_checkpoint_url': 'https://github.com/deezer/spleeter/releases/download/v1.4.0/5stems.tar.gz',
                'official_checkpoint_sha256': '25a1e87eb5f75cc72a4d2d5467a0a50ac75f05611f877c278793742513cc7218'}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def stage_roformer(cache, target):
    from music_studio.roformer_assets import MODELS, CHECKPOINT_SHA, WEIGHT_LICENSE, SOURCE_REVISION, PORT_REVISION
    target.mkdir(parents=True, exist_ok=True)
    for meta in MODELS.values():
        destination = cache / meta['file']
        if not destination.is_file() or destination.stat().st_size != meta['bytes'] or digest(destination) != meta['sha256']:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix('.part')
            try:
                with urllib.request.urlopen(meta['url'], timeout=120) as source, temporary.open('wb') as output:
                    count = 0
                    while block := source.read(1024 * 1024):
                        count += len(block)
                        if count > meta['bytes']:
                            raise ValueError('RoFormer asset exceeds its pinned size.')
                        output.write(block)
                if count != meta['bytes'] or digest(temporary) != meta['sha256']:
                    raise ValueError('RoFormer asset checksum mismatch.')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        shutil.copy2(destination, target / meta['file'])
    notices = ROOT / 'tools/roformer'
    for name in ('LICENSE-MSST.txt', 'LICENSE-Architecture.txt', 'LICENSE-Port.txt', 'NOTICE.txt'):
        shutil.copy2(notices / name, target / name)
    manifest = {'models': MODELS, 'license': 'MIT', 'checkpoint_sha256': CHECKPOINT_SHA,
                'weight_license_evidence': WEIGHT_LICENSE, 'source_revision': SOURCE_REVISION,
                'port_revision': PORT_REVISION, 'sample_rate': 44100, 'segment_samples': 485100,
                'stems': ['drums', 'bass', 'other', 'vocals'], 'precision': 'FP32'}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def stage_instruments(cache, target):
    from music_studio.instrument_assets import MODELS, CHECKPOINT_SHA, WEIGHT_LICENSE, SOURCE_REVISION, SELECTED, ORIGINAL_HEADS
    if len(MODELS) != 19:
        raise ValueError('The instrument model pins are incomplete.')
    target.mkdir(parents=True, exist_ok=True)
    for meta in MODELS.values():
        destination = cache / meta['file']
        if not destination.is_file() or destination.stat().st_size != meta['bytes'] or digest(destination) != meta['sha256']:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix('.part')
            try:
                with urllib.request.urlopen(meta['url'], timeout=120) as source, temporary.open('wb') as output:
                    count = 0
                    while block := source.read(1048576):
                        count += len(block)
                        if count > meta['bytes']:
                            raise ValueError('Instrument asset exceeds its pinned size.')
                        output.write(block)
                if count != meta['bytes'] or digest(temporary) != meta['sha256']:
                    raise ValueError('Instrument asset checksum mismatch.')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        shutil.copy2(destination, target / meta['file'])
    for name in ('LICENSE-MSST.txt', 'LICENSE-Architecture.txt', 'LICENSE-Port.txt'):
        shutil.copy2(ROOT / 'tools/roformer' / name, target / name)
    shutil.copy2(ROOT / 'tools/instruments/NOTICE.txt', target / 'NOTICE.txt')
    manifest = {'models': MODELS, 'license': 'MIT', 'checkpoint_sha256': CHECKPOINT_SHA,
                'weight_license_evidence': WEIGHT_LICENSE, 'source_revision': SOURCE_REVISION,
                'selected': list(SELECTED), 'original_heads': list(ORIGINAL_HEADS),
                'sample_rate': 44100, 'segment_samples': 882000,
                'outputs': ['guitar', 'strings', 'brass', 'synths', 'other'], 'precision': 'FP32'}
    (target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--arch', choices=NODE_SHA, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    stage_stems(work / 'stem-models', ROOT / 'music_studio/stem_models')
    stage_piano(work / 'stem-models/piano', ROOT / 'music_studio/stem_models/piano')
    stage_roformer(work / 'stem-models/roformer', ROOT / 'music_studio/stem_models/roformer')
    stage_instruments(work / 'stem-models/instruments', ROOT / 'music_studio/stem_models/instruments')
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
    prefix = 'node-v22.20.0-darwin-arm64'
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
