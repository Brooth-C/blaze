"""Reuse immutable, checksum-verified Blaze model/native releases for Android.

Native code is unchanged from v4.1.29; its matching source archive stays at the
documented immutable release URL. Only reviewed models from the Windows release
are copied. This avoids rebuilding the same native libraries/checkpoints in CI.
"""
from pathlib import Path
import argparse
import hashlib
import shutil
import urllib.request
import zipfile
import json
import io

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://github.com/Brooth-C/blaze/releases/download/'
PACKAGES = {
    'native.apk': ('v4.1.29/Blaze-Android-Preview.apk', 'd7dbd408b2c634334ec2865ab9ad50450668d740da9985119ae70f1ccbaa05c1'),
    'models.zip': ('windows-v0.6.0/Blaze-Windows.zip', '73bfa1bc0ce0657bb2792b5552c6614844fee3ebbea3bdccfa64ed4c659f96dc'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    for name, (url, checksum) in PACKAGES.items():
        target = args.work / name
        if not target.is_file() or digest(target) != checksum:
            with urllib.request.urlopen(BASE + url, timeout=120) as response, target.open('wb') as output:
                shutil.copyfileobj(response, output, 1024 * 1024)
        if digest(target) != checksum:
            raise ValueError('Immutable release checksum mismatch: ' + name)
    main_root = ROOT / 'android/app/src/main'
    with zipfile.ZipFile(args.work / 'native.apk') as archive:
        for abi in ('arm64-v8a', 'x86_64'):
            for name in ('libblaze_ffmpeg.so', 'libblaze_ffprobe.so', 'libblaze_qjs.so', 'libvlc.so', 'libvlcjni.so'):
                destination = main_root / 'jniLibs' / abi / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read('lib/' + abi + '/' + name))
        for member in archive.namelist():
            if member.startswith('assets/licenses/') and not member.endswith('/'):
                suffix = Path(member.removeprefix('assets/licenses/'))
                if '..' in suffix.parts:
                    raise ValueError('Invalid notice path')
                destination = main_root / 'assets/licenses' / suffix
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
    model_root = main_root / 'assets/musicstudio_models'
    model_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.work / 'models.zip') as archive:
        prefix = 'Blaze/_internal/music_studio/models/'
        assets = set()
        for name in ('manifest.json', 'structured_manifest.json', 'rhythm_manifest.json'):
            content = archive.read(prefix + name)
            metadata = json.loads(content)
            (model_root / name).write_bytes(content)
            assets.add(metadata['frontend']['file'])
            models = metadata.get('models')
            if isinstance(models, dict):
                assets.update(model['file'] for model in models.values())
            elif isinstance(models, list):
                assets.update(model['file'] for model in models)
            else:
                assets.add(metadata['network']['file'])
        assets.update(('LICENSE-BTC.txt', 'LICENSE-MusicXLab.txt', 'LICENSE-Librosa.txt', 'LICENSE-BeatThis.txt'))
        for name in assets:
            if Path(name).name != name:
                raise ValueError('Invalid model path')
            content = archive.read(prefix + name)
            (model_root / name).write_bytes(content)
            # Local parity suites use the same checked model assets.
            local = ROOT / 'music_studio/models' / name
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(content)
        for name in ('manifest.json', 'structured_manifest.json', 'rhythm_manifest.json'):
            shutil.copy2(model_root / name, ROOT / 'music_studio/models' / name)
    url = 'https://repo.maven.apache.org/maven2/org/videolan/android/libvlc-all/3.7.7/libvlc-all-3.7.7.aar'
    with urllib.request.urlopen(url, timeout=120) as response:
        bindings = response.read()
    if hashlib.sha256(bindings).hexdigest() != 'b48dab96e0e90e34cce3861963500c144a5aadb1b249d501d6a4b104d849e61b':
        raise ValueError('Official LibVLC bindings checksum mismatch')
    target = ROOT / 'android/app/libs/libvlc-java.aar'
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(bindings)) as source, zipfile.ZipFile(target, 'w') as output:
        for member in source.infolist():
            if not member.filename.startswith('jni/'):
                output.writestr(member, source.read(member.filename))
    print('Verified native libraries, model assets and official Java bindings staged.')


if __name__ == '__main__':
    main()
