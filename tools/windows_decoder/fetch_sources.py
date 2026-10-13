from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib, json, shutil, urllib.request

root = Path(__file__).resolve().parent
catalog = [
    ('w64devkit-x64-2.10.0.7z.exe', 'https://github.com/skeeto/w64devkit/releases/download/v2.10.0/w64devkit-x64-2.10.0.7z.exe', '18d0a4c71a166f8401ab6305781bec5882b40b5e06ba9807c61cb5f3b3c6325e', 'build tool only'),
    ('ffmpeg-7.1.3.tar.xz', 'https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz', 'f0bf043299db9e3caacb435a712fc541fbb07df613c4b893e8b77e67baf3adbe', 'LGPL-2.1-or-later; GPL disabled'),
    ('lame-3.100.tar.gz', 'https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz', 'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e', 'LGPL-2.0-or-later'),
    ('ogg-1.3.5.tar.gz', 'https://github.com/xiph/ogg/archive/refs/tags/v1.3.5.tar.gz', 'f6f1b04cfa4e98b70ffe775d5e302d9c6b98541f05159af6de2d6617817ed7d6', 'BSD-3-Clause'),
    ('vorbis-1.3.7.tar.gz', 'https://github.com/xiph/vorbis/archive/refs/tags/v1.3.7.tar.gz', '270c76933d0934e42c5ee0a54a36280e2d87af1de3cc3e584806357e237afd13', 'BSD-3-Clause'),
    ('opus-1.5.2.tar.gz', 'https://github.com/xiph/opus/archive/refs/tags/v1.5.2.tar.gz', '9480e329e989f70d69886ded470c7f8cfe6c0667cc4196d4837ac9e668fb7404', 'BSD-3-Clause'),
]
directory = root / 'downloads'
directory.mkdir(parents=True, exist_ok=True)
def fetch(item):
    name, url, expected, license = item
    path = directory / name
    if not path.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'Blaze-decoder-source-build/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response, path.open('wb') as destination:
            shutil.copyfileobj(response, destination)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected and digest != expected:
        raise RuntimeError('Artifact checksum mismatch: ' + name)
    print(name, path.stat().st_size, digest, flush=True)
    return {'file': name, 'url': url, 'sha256': digest, 'bytes': path.stat().st_size, 'license': license}
with ThreadPoolExecutor(max_workers=3) as pool:
    assets = list(pool.map(fetch, catalog))
(root / 'sources-manifest.json').write_text(json.dumps({'ffmpeg_tag': 'n7.1.3', 'ffmpeg_commit': 'f46e514491172d15bd74b4abb1814cd2f05a763e', 'assets': assets}, indent=2) + '\n', encoding='utf-8')
