"""Maintain an explicit release catalog without replacing published binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load_catalog(path=None):
    catalog = json.loads((path or ROOT / 'tools/release_catalog.json').read_text(encoding='utf-8'))
    if catalog.get('schema') != 1 or not re.fullmatch(r'v\d+\.\d+\.\d+', catalog.get('tag', '')):
        raise ValueError('Invalid release catalog schema or tag')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', catalog.get('repository', '')):
        raise ValueError('Invalid source repository')
    assets = catalog.get('assets', [])
    names = [asset.get('name', '') for asset in assets]
    if not names or len(names) != len(set(names)):
        raise ValueError('Release catalog must have unique assets')
    for asset in assets:
        if not re.fullmatch(r'[\w.-]+', asset.get('name', '')):
            raise ValueError('Invalid asset filename')
        if not re.fullmatch(r'[\w.-]+', asset.get('source_tag', '')):
            raise ValueError('Every asset needs an immutable source tag')
        if not re.fullmatch(r'[0-9a-f]{64}', asset.get('sha256', '')):
            raise ValueError('Every asset needs a pinned SHA256')
        if not isinstance(asset.get('size'), int) or asset['size'] <= 0:
            raise ValueError('Every asset needs a pinned positive byte size')
        if not all(asset.get(key) for key in ('platform', 'component_version', 'description')):
            raise ValueError('Every asset needs its platform, version and description')
    native = catalog.get('android_native_sources', {})
    if (not re.fullmatch(r'[0-9a-f]{64}', native.get('sha256', ''))
            or not isinstance(native.get('size'), int) or native['size'] <= 0):
        raise ValueError('Android native source archive needs a pinned SHA256 and byte size')
    if (not re.fullmatch(r'[\w.-]+', native.get('name', ''))
            or not re.fullmatch(r'[\w.-]+', native.get('source_tag', ''))
            or native.get('url') != f"https://github.com/{catalog['repository']}/releases/download/{native['source_tag']}/{native['name']}"):
        raise ValueError('Android native sources must link to a published archive')
    return catalog


def target_repository(catalog):
    return os.environ.get('GH_REPO', catalog['repository'])


def page(catalog):
    base = f'https://github.com/{target_repository(catalog)}'
    source_base = f"https://github.com/{catalog['repository']}"
    rows = '\n'.join(
        f"| {asset['platform']} | [Download {'APK' if asset['name'].endswith('.apk') else 'ZIP'}]({base}/releases/download/{catalog['tag']}/{asset['name']}) |"
        for asset in catalog['assets'])
    provenance = '\n'.join(
        f"- **{asset['name']}** · version {asset['component_version']} · [{asset['source_tag']}]({source_base}/releases/tag/{asset['source_tag']}) · "
        f"{asset['size']:,} bytes · SHA256 `{asset['sha256']}`"
        for asset in catalog['assets'])
    native = catalog['android_native_sources']
    mac_apps = any(asset['name'] == 'Blaze-Mac-arm64.zip' for asset in catalog['assets'])
    desktop = 'Windows, macOS and Android' if mac_apps else 'Windows and Android'
    terminals = 'Linux and Termux' if mac_apps else 'macOS, Linux and Termux'
    mac_note = f'Mac previews are ad-hoc signed without Apple notarization; see the [Mac guide]({base}/blob/main/docs/MACOS.md) for installation.\n' if mac_apps else ''
    versions = '; '.join(f"{asset['platform']}: {asset['component_version']}" for asset in catalog['assets'])
    return f'''## Download Blaze

Choose **one download** for your platform. Extract ZIPs completely before opening
Blaze; install the Android APK directly.

| Platform | Download |
| --- | --- |
{rows}

{desktop} include Music Studio with advanced offline chord analysis,
audio/video import, playback and automatic beat/meter detection. Android remains
a preview. {terminals} retain the existing terminal app.
{mac_note}

**{catalog['tag']} is a distribution refresh:** it brings these existing platform
builds together. Component versions: {versions}.

[Setup guides]({base}/blob/main/docs/README.md) · [Android guide]({base}/blob/main/docs/ANDROID-APK.md) · [Help]({base}/blob/main/SUPPORT.md)

## Sources and licenses

Windows corresponding decoder sources and license notices are inside its ZIP.
Mac apps include their matching decoder sources and license notices inside the app.
Android's matching native decoder sources remain available in the
[corresponding-source archive]({native['url']})
({native['size']:,} bytes; SHA256 `{native['sha256']}`). Android licenses and
component replacement instructions are documented in the Android guide.
GitHub's automatic source archives contain the Blaze source for this tag.

<details>
<summary>Versions, checksums and original builds</summary>


These are the original, unchanged binaries. Checksums are included here so no
additional checksum download is needed.

{provenance}

</details>

Earlier platform releases remain available for rollback.
'''


def gh(*args, optional=False):
    result = subprocess.run(['gh', *args], text=True, capture_output=True)
    if result.returncode:
        if optional and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip() or 'GitHub command failed')
    return result.stdout


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def verify_files(directory, assets):
    for asset in assets:
        path = directory / asset['name']
        if path.stat().st_size != asset['size'] or digest(path) != asset['sha256']:
            raise ValueError(f"Downloaded size or digest mismatch for {asset['name']}")


def verify_asset(asset, expected):
    if (asset.get('state') != 'uploaded'
            or asset.get('size') != expected['size']
            or asset.get('digest') != 'sha256:' + expected['sha256']):
        raise ValueError(f"{expected['name']} differs or is incomplete; existing assets are preserved")


def verify_target(target, catalog, require_all=False):
    existing = {asset['name']: asset for asset in target.get('assets', [])}
    allowed = {asset['name'] for asset in catalog['assets']}
    if set(existing) - allowed:
        raise ValueError('Catalog release has unexpected assets; existing assets are preserved')
    for expected in catalog['assets']:
        if expected['name'] in existing:
            verify_asset(existing[expected['name']], expected)
        elif require_all:
            raise ValueError(f"Missing catalog asset {expected['name']}")
    return existing


def mirror(tag, catalog=None):
    catalog = catalog or load_catalog()
    if tag != catalog['tag']:
        raise ValueError('Catalog may only be mirrored to its declared tag')
    repo = target_repository(catalog)
    target_json = gh('api', f'repos/{repo}/releases/tags/{tag}', optional=True)
    if target_json is None:
        print('Unified release is not published yet; existing releases are preserved.')
        return False
    target = json.loads(target_json)
    if target.get('draft'):
        print('Unified release is still a draft; its publisher will complete it.')
        return False
    existing = verify_target(target, catalog)
    sources = {}
    for expected in [*catalog['assets'], catalog['android_native_sources']]:
        source_tag = expected['source_tag']
        if source_tag not in sources:
            source = json.loads(gh('api', f"repos/{catalog['repository']}/releases/tags/{source_tag}"))
            if source.get('draft'):
                raise ValueError(f'Source release {source_tag} is still a draft')
            sources[source_tag] = {asset['name']: asset for asset in source.get('assets', [])}
        if expected['name'] not in sources[source_tag]:
            raise ValueError(f"Source release is missing {expected['name']}")
        verify_asset(sources[source_tag][expected['name']], expected)
    missing = [asset for asset in catalog['assets'] if asset['name'] not in existing]
    if not missing:
        print('All catalog downloads match their pinned original builds.')
        return True
    with tempfile.TemporaryDirectory(prefix='blaze-release-') as tmp:
        directory = Path(tmp)
        for source_tag in dict.fromkeys(asset['source_tag'] for asset in missing):
            command = ['release', 'download', source_tag, '--repo', catalog['repository'], '--dir', str(directory)]
            for asset in missing:
                if asset['source_tag'] == source_tag:
                    command += ['--pattern', asset['name']]
            gh(*command)
        verify_files(directory, missing)
        try:
            gh('release', 'upload', tag, *(str(directory / asset['name']) for asset in missing), '--repo', repo)
        except RuntimeError:
            # Another validated publisher may have completed the same mirror.
            # Never use --clobber, delete a binary or accept different contents.
            latest = json.loads(gh('api', f'repos/{repo}/releases/tags/{tag}'))
            verify_target(latest, catalog, require_all=True)
        else:
            latest = json.loads(gh('api', f'repos/{repo}/releases/tags/{tag}'))
            verify_target(latest, catalog, require_all=True)
    print('Verified missing catalog downloads attached; existing builds preserved.')
    return True


def refresh(catalog):
    if not mirror(catalog['tag'], catalog):
        return
    with tempfile.TemporaryDirectory(prefix='blaze-release-notes-') as tmp:
        notes = Path(tmp) / 'RELEASE-PAGE.md'
        notes.write_text(page(catalog), encoding='utf-8')
        # Editing notes deliberately does not change the tag, prerelease or Latest state.
        gh('release', 'edit', catalog['tag'], '--repo', target_repository(catalog), '--notes-file', str(notes))
    print('Unified release navigation refreshed; Latest state preserved.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--notes', type=Path)
    parser.add_argument('--mirror')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    if args.notes:
        args.notes.write_text(page(catalog), encoding='utf-8')
    if args.mirror:
        mirror(args.mirror, catalog)
    if args.refresh:
        refresh(catalog)


if __name__ == '__main__':
    main()
