from pathlib import Path
import hashlib, json, shutil, zipfile
root = Path(__file__).resolve().parent
output = root / 'output'
licenses = output / 'licenses'
licenses.mkdir(parents=True, exist_ok=True)
files = [
    ('ffmpeg-7.1.3/COPYING.LGPLv2.1', 'FFmpeg-LGPL-2.1.txt'),
    ('ffmpeg-7.1.3/LICENSE.md', 'FFmpeg-LICENSE.md'),
    ('lame-3.100/COPYING', 'LAME-LGPL.txt'),
    ('ogg-1.3.5/COPYING', 'Ogg-BSD.txt'),
    ('vorbis-1.3.7/COPYING', 'Vorbis-BSD.txt'),
    ('opus-1.5.2/COPYING', 'Opus-BSD.txt'),
]
for relative, name in files:
    shutil.copy2(root / 'src' / relative, licenses / name)
shutil.copy2(root / 'toolchain/w64devkit/COPYING.MinGW-w64-runtime.txt', licenses / 'MinGW-w64-runtime.txt')
shutil.copy2(root / 'GCC-Runtime-Exception.txt', licenses / 'GCC-Runtime-Exception.txt')
readme = '''Blaze Windows FFmpeg decoder: matching source and build instructions

FFmpeg 7.1.3, LGPL 2.1 or later. GPL, nonfree, version3 components disabled.
LAME 3.100 encoder only, LGPL 2.0 or later; decoder/frontend disabled.
Ogg 1.3.5, Vorbis 1.3.7 and Opus 1.5.2: BSD licences retained.
These sources are unmodified. Build configuration is in build.sh/config.mak.
Blaze invokes FFmpeg as a separate replaceable executable. FFmpeg is not linked
into Blaze. This source archive includes the corresponding application code for
rebuilding FFmpeg and its LGPL library, plus exact sources of codec dependencies.

Rebuild on Windows x64 with Python 3.12+ and the pinned portable w64devkit 2.10.0:
1. Unzip this archive into an empty directory.
2. Run python fetch_sources.py (checks all SHA256 hashes; sources already included).
3. Extract downloads/w64devkit-x64-2.10.0.7z.exe into toolchain/ using -y -otoolchain.
   The compiler is build-only and is not part of the shipped decoder.
4. Run python extract_sources.py.
5. In PowerShell set the process PATH to toolchain/w64devkit/bin plus existing PATH.
6. Run toolchain/w64devkit/bin/sh.exe build.sh. Result: output/bin/ffmpeg.exe.
   No global installation, PATH change, or administrator privilege is needed.
   The build script uses four parallel jobs; BLAZE_CODEC_JOBS can override it.

The compiled FFmpeg command-line tools use GCC's runtime library exception and
MinGW-w64's platform runtime; the build-only compiler is separately licensed.
Author copyright notices and dependency licences are retained in their sources.
Do not apply Blaze's own licence or redistribution restrictions to these files.
'''
(output / 'SOURCE-README.txt').write_text(readme, encoding='utf-8')
manifest = json.loads((root / 'sources-manifest.json').read_text(encoding='utf-8'))
exe = output / 'bin' / 'ffmpeg.exe'
manifest['binary'] = {'file': 'ffmpeg.exe', 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(), 'bytes': exe.stat().st_size}
(output / 'decoder-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
archive = output / 'FFmpeg-LGPL-Corresponding-Sources.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as bundle:
    for asset in manifest['assets']:
        if asset['file'].endswith('.exe'):
            continue
        path = root / 'downloads' / asset['file']
        bundle.write(path, 'downloads/' + path.name)
    for name in ('fetch_sources.py', 'extract_sources.py', 'build.sh', 'sources-manifest.json', 'package_sources.py', 'GCC-Runtime-Exception.txt'):
        bundle.write(root / name, name)
    for name in ('version.txt', 'license.txt', 'SOURCE-README.txt', 'decoder-manifest.json'):
        bundle.write(output / name, name)
    bundle.write(root / 'build/ffmpeg/ffbuild/config.mak', 'config.mak')
    for path in licenses.iterdir():
        bundle.write(path, 'licenses/' + path.name)
print('Matching sources:', archive, archive.stat().st_size)
