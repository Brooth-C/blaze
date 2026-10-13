from pathlib import Path
import tarfile
root = Path(__file__).resolve().parent
source = root / 'src'
source.mkdir(exist_ok=True)
for name in ('ffmpeg-7.1.3.tar.xz', 'lame-3.100.tar.gz', 'ogg-1.3.5.tar.gz', 'vorbis-1.3.7.tar.gz', 'opus-1.5.2.tar.gz'):
    with tarfile.open(root / 'downloads' / name) as archive:
        directory = archive.getmembers()[0].name.split('/')[0]
        if (source / directory).exists():
            continue
        archive.extractall(source, filter='data')
    print('Extracted', directory)
