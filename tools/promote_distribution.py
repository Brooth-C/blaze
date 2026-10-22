"""Publish a distribution from immutable releases and successful native build proof."""
import os
import re
from pathlib import Path
import tempfile

try:
    from tools import release_page as release
    from tools import promote_mac_release as publisher
except ModuleNotFoundError:
    import release_page as release
    import promote_mac_release as publisher

REPOSITORY = 'Brooth-C/blaze'
NATIVE_SOURCES = dict(name='Blaze-Android-Native-Sources.tar.gz', source_tag='v4.1.29',
                      size=374676937, sha256='c2eeadf7bbc8be426ead9248fa69e4a5ce5c490c5484669495e684a3081d226e')
ORIGINS = {
    'Blaze-Windows.zip': 'windows-v0.7.0',
    'Blaze-Android-Preview.apk': 'android-v0.11.0',
    'Blaze-Mac-arm64.zip': 'macos-v0.7.0-preview',
    'Blaze-Mac-x86_64.zip': 'macos-v0.7.0-preview',
    'Blaze-Linux-x86_64.tar.gz': 'linux-v0.7.0-preview',
    'Blaze-Linux-Installer.zip': 'v4.1.29',
    'Blaze-Termux-Installer.zip': 'v4.1.29',
}
WORKFLOWS = {
    'desktop': ('Windows and Linux desktop packages', {'windows', 'linux', 'publish'}),
    'macos': ('Blaze macOS app', {'Mac app / arm64', 'Mac app / x86_64', 'Publish tested Mac app'}),
    'android': ('Android offline Studio validation', {'Build Android APK', 'Publish Android preview'}),
}
INPUTS = (
    'music_studio', 'android', 'blaze.py', 'installers/linux-desktop',
    'music_studio/chords.py', 'music_studio/evidence.py',
    'music_studio/lv_frontend.py', 'music_studio/structured.py', 'music_studio/models',
    'LICENSE.txt', 'THIRD-PARTY-NOTICES.md', 'docs/LINUX-DESKTOP.md',
    'tools/build_windows_studio.py', 'tools/build_linux_studio.py', 'tools/stage_desktop_release.py',
    'tools/publish_desktop_release.py', 'tests/Blaze-Desktop-Package-Tests.py', 'tests/Blaze-Mac-Package-Tests.py',
    'tools/build_macos_studio.py', 'tools/build_macos_downloader.py', 'tools/stage_macos_studio.py',
    'tools/macos_decoder', 'tools/stage_android_studio.py', 'tools/sync_android_harmony.py',
    '.github/workflows/desktop-release.yml', '.github/workflows/macos-app.yml',
    '.github/workflows/android-apk.yml', 'docs/assets/blaze-logo.png',
)
# These inputs cannot affect the unchanged Windows, Linux or macOS packages.
ANDROID_ONLY_INPUTS = {
    'android', 'tools/stage_android_studio.py', 'tools/sync_android_harmony.py',
    '.github/workflows/android-apk.yml',
}
# sync_android_harmony.py copies exactly these four Python modules. The complete
# Android tree covers the Gradle build, app sources, embedded assets and tests;
# stage_android_studio.py pins the native/model releases and Java bindings.
# Include the local model tree conservatively for parity/provenance, along with
# common licensing and branding. Desktop hosts, web assets and desktop packaging
# do not feed the APK, so their parent music_studio tree is not an Android input.
ANDROID_INPUTS = ANDROID_ONLY_INPUTS | {
    'music_studio/chords.py', 'music_studio/evidence.py',
    'music_studio/lv_frontend.py', 'music_studio/structured.py', 'music_studio/models',
    'LICENSE.txt', 'THIRD-PARTY-NOTICES.md', 'docs/assets/blaze-logo.png',
}


def platform_tree(tree, platform):
    if platform == 'android':
        if not ANDROID_INPUTS <= tree.keys():
            raise ValueError('Incomplete Android application input tree')
        return {path: tree[path] for path in ANDROID_INPUTS}
    return {path: entry for path, entry in tree.items()
            if path not in ANDROID_ONLY_INPUTS}


def input_tree(commit):
    tree_sha = publisher.api(f'git/commits/{commit}')["tree"]["sha"]
    tree = publisher.api(f'git/trees/{tree_sha}?recursive=1')
    entries = {item['path']: (item['type'], item['sha']) for item in tree['tree']}
    if tree.get('truncated') or any(path not in entries for path in INPUTS):
        raise ValueError('Incomplete application input tree')
    return {path: entries[path] for path in INPUTS}


def validate(catalog, main_sha):
    if (catalog['repository'] != REPOSITORY or catalog['tag'] != 'v4.3.3'
            or os.environ.get('GH_REPO', REPOSITORY) != REPOSITORY
            or os.environ.get('GITHUB_REPOSITORY', REPOSITORY) != REPOSITORY
            or {a['name']: a['source_tag'] for a in catalog['assets']} != ORIGINS):
        raise ValueError('Unexpected distribution or platform origins')
    proofs = catalog.get('native_validation', {})
    if set(proofs) != set(WORKFLOWS):
        raise ValueError('Every native platform requires validation proof')
    main_tree = input_tree(main_sha)
    for key, (name, required_jobs) in WORKFLOWS.items():
        proof = proofs[key]
        run_id, head = proof.get('run_id'), proof.get('head_sha', '')
        if type(run_id) is not int or run_id <= 0 or not re.fullmatch(r'[0-9a-f]{40}', head):
            raise ValueError('Invalid native run ID or source SHA')
        run = publisher.api(f'actions/runs/{run_id}')
        if (run.get('name') != name or run.get('status') != 'completed'
                or run.get('conclusion') != 'success' or run.get('head_sha') != head
                or run.get('event') not in ('push', 'workflow_dispatch')
                or run.get('head_branch') != 'main'
                or run.get('repository', {}).get('full_name') != REPOSITORY
                or run.get('head_repository', {}).get('full_name') != REPOSITORY):
            raise ValueError('A native workflow did not successfully publish this main source')
        jobs = publisher.api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
        passed = {job['name'] for job in jobs if job.get('conclusion') == 'success'}
        if not required_jobs <= passed:
            raise ValueError('Required native jobs or publication did not pass')
        if key == 'android' and not {'Android tests / API 29', 'Android tests / API 35'} <= passed:
            raise ValueError('Both Android emulator versions must pass')
        if platform_tree(input_tree(head), key) != platform_tree(main_tree, key):
            raise ValueError('Application inputs changed after native validation')
    for tag in set(ORIGINS.values()):
        source = publisher.api(f'releases/tags/{tag}')
        if source.get('draft'):
            raise ValueError('A platform release is still a draft')
        platform = ('android' if tag.startswith('android-') else 'macos' if tag.startswith('macos-')
                    else 'desktop' if tag.startswith(('windows-', 'linux-')) else None)
        if platform and source.get('target_commitish') != proofs[platform]['head_sha']:
            raise ValueError('A platform release targets a different source from its native proof')
        expected = [asset for asset in catalog['assets'] if asset['source_tag'] == tag]
        available = {asset['name']: asset for asset in source['assets']}
        for asset in expected:
            if asset['name'] not in available:
                raise ValueError('A pinned platform package is absent')
            release.verify_asset(available[asset['name']], asset)
    native = catalog['android_native_sources']
    if any(native.get(key) != value for key, value in NATIVE_SOURCES.items()):
        raise ValueError('The Android decoder source archive must match the reviewed native build')
    source = publisher.api(f"releases/tags/{native['source_tag']}")
    matching = [asset for asset in source['assets'] if asset['name'] == native['name']]
    if len(matching) != 1:
        raise ValueError('Matching Android decoder sources are absent')
    release.verify_asset(matching[0], native)


def promote(catalog):
    main_sha = publisher.current_main()
    if os.environ.get('GITHUB_SHA', main_sha) != main_sha:
        print('A newer main source is awaiting validation; publication skipped.')
        return
    validate(catalog, main_sha)
    with tempfile.TemporaryDirectory(prefix='blaze-distribution-') as temporary:
        directory = Path(temporary)
        for asset in catalog['assets']:
            release.gh('release', 'download', asset['source_tag'], '--repo', REPOSITORY,
                       '--pattern', asset['name'], '--dir', str(directory))
        release.verify_files(directory, catalog['assets'])
        notes = directory / 'release-notes.md'
        notes.write_text(release.page(catalog), encoding='utf-8')
        publisher.publish(catalog['tag'], 'Blaze 4.3.3 · smoother Android search and video playback',
                          catalog['assets'], directory, notes, main_sha, False, main_sha)
        if publisher.api('releases/latest')['tag_name'] != catalog['tag']:
            raise ValueError('The verified distribution is not GitHub Latest')
    print('Published the verified seven-download Blaze distribution.')


if __name__ == '__main__':
    promote(release.load_catalog())
