"""Opt-in live metadata check through the actual desktop discovery boundary.

No media is downloaded. Run on a network-enabled Mac runner, not offline source
test jobs. The receipt distinguishes live provider access from fixture UI tests.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.discovery import Discovery  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tools', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    executable = args.tools / 'yt-dlp' if args.tools else Path(shutil.which('yt-dlp') or '')
    if not executable.is_file():
        raise RuntimeError('The tested downloader is missing.')
    version = subprocess.run([str(executable), '--version'], capture_output=True, text=True,
                             check=True, timeout=10).stdout.strip()
    if version != '2026.10.26':
        raise RuntimeError('Live search must use the exact pinned downloader.')
    receipt = {'ok': False, 'downloader': version, 'live': True, 'audioDownloaded': False, 'checks': []}
    with tempfile.TemporaryDirectory(prefix='blaze-live-search-') as directory:
        catalogue = Discovery(Path(directory), executable.parent, 'ffmpeg')
        try:
            for scope in ('all', 'songs'):
                identity = catalogue.request({'action': 'search', 'query': 'acoustic piano',
                                              'filter': scope, 'limit': 3})['requestId']
                deadline = time.monotonic() + 35
                while True:
                    result = catalogue.status(identity)
                    if result['status'] != 'pending':
                        break
                    if time.monotonic() > deadline:
                        catalogue.cancel(identity)
                        raise RuntimeError('Live search did not settle within its deadline.')
                    time.sleep(.1)
                count = len(result['items'])
                receipt['checks'].append({'filter': scope, 'status': result['status'], 'count': count,
                                          'error': result['error']})
            receipt['ok'] = all(row['status'] == 'ready' and row['count'] > 0 for row in receipt['checks'])
        finally:
            catalogue.close()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    if not receipt['ok']:
        raise RuntimeError('The live YouTube provider search did not return usable recordings.')


if __name__ == '__main__':
    main()
