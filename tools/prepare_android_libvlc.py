"""Keep official Java bindings; package only the separately built LGPL native engine."""
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
import io
import tarfile

app = Path('android/app')
base = 'https://repo.maven.apache.org/maven2/org/videolan/android/libvlc-all/3.7.7/'
with urlopen(base + 'libvlc-all-3.7.7.aar', timeout=60) as response:
    upstream = response.read()
output = app / 'libs/libvlc-java.aar'
output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(io.BytesIO(upstream)) as source, ZipFile(output, 'w') as target:
    for member in source.infolist():
        if not member.filename.startswith('jni/'):
            target.writestr(member, source.read(member.filename))
assert not any(name.endswith('.so') for name in ZipFile(output).namelist())
with urlopen(base + 'libvlc-all-3.7.7-sources.jar', timeout=60) as response:
    bindings = response.read()
archive = app / 'src/main/Blaze-Android-Native-Sources.tar.gz'
extra = app / 'src/main/Blaze-LibVLC-Sources.tar.gz'
temporary = archive.with_suffix('.new')
with tarfile.open(archive, 'r:gz') as original, tarfile.open(extra, 'r:gz') as vlc, tarfile.open(temporary, 'w:gz') as combined:
    for source, prefix in ((original, ''), (vlc, 'libvlc/')):
        for member in source:
            data = source.extractfile(member) if member.isfile() else None
            member.name = prefix + member.name.lstrip('./')
            combined.addfile(member, data)
    member = tarfile.TarInfo('libvlc/libvlc-all-3.7.7-sources.jar')
    member.size = len(bindings)
    combined.addfile(member, io.BytesIO(bindings))
temporary.replace(archive)
extra.unlink()
