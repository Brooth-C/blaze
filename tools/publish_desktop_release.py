"""Publish a new immutable platform release only after native workflow gates pass."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--platform', choices=('Windows', 'Linux'), required=True)
    args = parser.parse_args()
    current = subprocess.check_output(['gh', 'api', f"repos/{os.environ['GH_REPO']}/git/ref/heads/main", '--jq', '.object.sha'], text=True).strip()
    if current != os.environ['GITHUB_SHA']:
        print('A newer source commit is awaiting validation; skipping publication.')
        return
    digest = hashlib.sha256(args.file.read_bytes()).hexdigest()
    probe = subprocess.run(['gh', 'release', 'view', args.tag, '--json', 'assets'], text=True, capture_output=True)
    if probe.returncode == 0:
        assets = {a['name']: a for a in json.loads(probe.stdout)['assets']}
        asset = assets[args.file.name]
        assert asset['size'] == args.file.stat().st_size and asset.get('digest') == 'sha256:' + digest, 'Published binaries are immutable'
        return
    notes = Path('docs/RELEASE-0.8.0.md').read_text(encoding='utf-8')
    notes += '\n\nPackage SHA256: `' + digest + '`\n'
    if args.platform == 'Windows':
        notes += '\nExtract the complete ZIP and run Blaze/Blaze.exe. Microsoft Edge WebView2 Runtime is required. This executable is not Authenticode-signed.\n'
    else:
        notes += '\nUbuntu 22.04 x86_64 desktop preview. Extract and run Blaze/Install-Blaze.sh. Python, GTK/WebKit and system FFmpeg prerequisites are documented in the archive. One-time dependency installation requires internet.\n'
    destination = Path('platform-release-notes.md')
    destination.write_text(notes, encoding='utf-8')
    command = ['gh', 'release', 'create', args.tag, str(args.file), '--target', current,
               '--title', 'Blaze for ' + args.platform + ' 0.8.0', '--notes-file', str(destination), '--latest=false']
    if args.platform == 'Linux':
        command.append('--prerelease')
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
