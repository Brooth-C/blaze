"""Render focused release notes and mirror verified Android release files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ANDROID_FILES = ('Blaze-Android-Preview.apk', 'SHA256SUMS-Android.txt',
                 'Blaze-Android-Native-Sources.tar.gz')


def versions():
    desktop = re.search(r'^VERSION = "([^"]+)"', (ROOT / 'blaze.py').read_text(encoding='utf-8'), re.M).group(1)
    android = re.search(r"versionName\s+['\"]([^'\"]+)['\"]", (ROOT / 'android/app/build.gradle').read_text(encoding='utf-8')).group(1)
    return desktop, android


def current_notes(history, version):
    match = re.search(r'^#{1,2} Blaze ' + re.escape(version) + r'\s*\n(.*?)(?=^#{1,2} Blaze |\Z)', history, re.M | re.S)
    if not match:
        raise ValueError(f'Missing release notes for {version}')
    return match.group(1).strip()


def page(version, android, history):
    repo = os.environ.get('GH_REPO', 'Brooth-C/blaze')
    base = f'https://github.com/{repo}'
    rows = '\n'.join(f'| {label} | [{label} download]({base}/releases/download/v{version}/{file}) |'
                     for label, file in [('Windows', 'Blaze-Windows-Installer.zip'),
                                         ('macOS', 'Blaze-Mac-Installer.zip'),
                                         ('Linux', 'Blaze-Linux-Installer.zip'),
                                         ('Android APK · preview', 'Blaze-Android-Preview.apk'),
                                         ('Android / Termux', 'Blaze-Termux-Installer.zip')])
    return f'''## Downloads

Choose your platform from **Assets** below. Extract installer ZIPs completely;
the Android APK installs directly. “Source code” archives are for development.

| Platform | File |
| --- | --- |
{rows}

[Setup guides]({base}/blob/main/docs/README.md) · [Help]({base}/blob/main/SUPPORT.md)

## Changes in {version}

{current_notes(history, version)}

## Android {android}

The Android APK is a separate debug-signed preview. Export files before
uninstalling an older build if its signing key prevents updating.
[Android notes and requirements]({base}/releases/tag/android-v{android}).

Installer checksums are in `SHA256SUMS.txt`; the APK checksum is in
`SHA256SUMS-Android.txt`. Native sources accompany the APK.
[Earlier changes]({base}/blob/main/docs/RELEASE-NOTES.md).
'''


def gh(*args, optional=False):
    result = subprocess.run(['gh', *args], text=True, capture_output=True)
    if result.returncode:
        if optional and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip() or 'GitHub command failed')
    return result.stdout


def verify_files(directory, assets):
    for name in ANDROID_FILES:
        digest = assets[name].get('digest', '')
        actual = 'sha256:' + hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if digest != actual:
            raise ValueError(f'Published digest mismatch for {name}')
    manifest = (directory / 'SHA256SUMS-Android.txt').read_text().split()
    if len(manifest) != 2 or manifest[1].lstrip('*') != ANDROID_FILES[0]:
        raise ValueError('Unexpected APK checksum manifest')
    actual = hashlib.sha256((directory / ANDROID_FILES[0]).read_bytes()).hexdigest()
    if manifest[0] != actual:
        raise ValueError('APK checksum mismatch')


def mirror(tag, android):
    repo = os.environ['GH_REPO']
    source = gh('api', f'repos/{repo}/releases/tags/android-v{android}', optional=True)
    target = gh('api', f'repos/{repo}/releases/tags/{tag}', optional=True)
    if source is None or target is None:
        print('Companion release is not published yet; its publisher will complete the mirror.')
        return
    source = json.loads(source)
    target = json.loads(target)
    if source.get('draft') or target.get('draft'):
        raise ValueError('Only published release assets may be mirrored')
    assets = {a['name']: a for a in source['assets']}
    if not all(name in assets and assets[name].get('state') == 'uploaded' for name in ANDROID_FILES):
        raise ValueError('Android release is missing required files')
    existing = {a['name']: a for a in target['assets']}
    missing = []
    for name in ANDROID_FILES:
        if name in existing:
            if not assets[name].get('digest') or existing[name].get('digest') != assets[name]['digest']:
                raise ValueError(f'{name} already differs: publish a new desktop version; existing assets are preserved')
        else:
            missing.append(name)
    if not missing:
        print('Verified Android companion files are already attached.')
        return
    with tempfile.TemporaryDirectory(prefix='blaze-release-') as tmp:
        directory = Path(tmp)
        command = ['release', 'download', f'android-v{android}', '--dir', str(directory)]
        for name in ANDROID_FILES:
            command += ['--pattern', name]
        gh(*command)
        verify_files(directory, assets)
        try:
            gh('release', 'upload', tag, *(str(directory / name) for name in missing))
        except RuntimeError:
            # Both publishers can reach this step together. Accept only an
            # identical completed mirror; never clobber an existing binary.
            latest = json.loads(gh('api', f'repos/{repo}/releases/tags/{tag}'))
            attached = {a['name']: a for a in latest['assets']}
            if not all(name in attached and attached[name].get('state') == 'uploaded'
                       and attached[name].get('digest') == assets[name]['digest']
                       for name in ANDROID_FILES):
                raise
    print('Verified Android companion files attached.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--notes', type=Path)
    parser.add_argument('--mirror')
    args = parser.parse_args()
    desktop, android = versions()
    if args.notes:
        args.notes.write_text(page(desktop, android, (ROOT / 'docs/RELEASE-NOTES.md').read_text(encoding='utf-8')), encoding='utf-8')
    if args.mirror:
        mirror(args.mirror, android)


if __name__ == '__main__':
    main()

