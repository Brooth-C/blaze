"""Build the portable Windows Studio from installed, pinned build dependencies."""
from pathlib import Path
import argparse
import shutil
import json
import hashlib
import PyInstaller.__main__

p = argparse.ArgumentParser()
p.add_argument('--ffmpeg', required=True, type=Path)
p.add_argument('--decoder-materials', required=True, type=Path,
               help='Output of tools/windows_decoder/package_sources.py')
p.add_argument('--ytdlp', required=True, type=Path)
p.add_argument('--node', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
p.add_argument('--work', required=True, type=Path)
a = p.parse_args()
decoder_manifest = json.loads((a.decoder_materials / 'decoder-manifest.json').read_text(encoding='utf-8'))
if hashlib.sha256(a.ffmpeg.read_bytes()).hexdigest() != decoder_manifest['binary']['sha256']:
    raise ValueError('Decoder sources must match the supplied executable.')
if not (a.decoder_materials / 'FFmpeg-LGPL-Corresponding-Sources.zip').is_file():
    raise ValueError('Matching decoder source archive is required.')
root = Path(__file__).resolve().parents[1]
shutil.copy2(root / 'docs/assets/blaze-logo.png', root / 'music_studio/web/blaze-logo.png')
a.work.mkdir(parents=True, exist_ok=True)
# Build a GUI-specific downloader copy without altering terminal installers.
downloader_stage = a.work.resolve() / 'desktop-source'
downloader_stage.mkdir(parents=True, exist_ok=True)
downloader_text = (root / 'blaze.py').read_text(encoding='utf-8')
flag = 'kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP'
if flag + ' | subprocess.CREATE_NO_WINDOW' not in downloader_text:
    downloader_text = downloader_text.replace(flag, flag + ' | subprocess.CREATE_NO_WINDOW')
(downloader_stage / 'blaze.py').write_text(downloader_text, encoding='utf-8')
# Ship only verified assets used by this release. Research/refined checkpoints
# remain outside the public bundle; all shipped model notices are retained.
model_source = root / 'music_studio/models'
model_stage = a.work.resolve() / 'models'
model_stage.mkdir(parents=True, exist_ok=True)
manifest = json.loads((model_source / 'manifest.json').read_text(encoding='utf-8'))
manifest['models'] = {key: value for key, value in manifest['models'].items() if key in ('major_minor', 'extended')}
assets = {manifest['frontend']['file'], *(m['file'] for m in manifest['models'].values())}
for name in ('structured_manifest.json', 'rhythm_manifest.json'):
    metadata = json.loads((model_source / name).read_text(encoding='utf-8'))
    assets.add(metadata['frontend']['file'])
    if 'models' in metadata:
        assets.update(m['file'] for m in metadata['models'])
    else:
        assets.add(metadata['network']['file'])
    assets.add(name)
assets.update(('LICENSE-BTC.txt', 'LICENSE-MusicXLab.txt', 'LICENSE-Librosa.txt', 'LICENSE-BeatThis.txt'))
for name in assets:
    if Path(name).name != name:
        raise ValueError('Model paths must remain inside the bundle.')
    shutil.copy2(model_source / name, model_stage / name)
(model_stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
# A fixed decoder name keeps the executable independent of the build machine.
decoder = a.work.resolve() / 'decoder' / 'ffmpeg.exe'
decoder.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(a.ffmpeg.resolve(), decoder)
args = ['--noconfirm', '--clean', '--windowed', '--onedir', '--name', 'Blaze',
        '--icon', str(root / 'docs/assets/blaze-logo.png'),
        '--distpath', str(a.output.resolve()), '--workpath', str(a.work.resolve() / 'pyinstaller'),
        '--specpath', str(a.work.resolve()), '--paths', str(downloader_stage), '--paths', str(root),
        '--add-data', str(root / 'music_studio/web') + ';music_studio/web',
        '--add-data', str(model_stage) + ';music_studio/models',
        '--add-binary', str(decoder) + ';bin',
        '--add-binary', str(a.ytdlp.resolve()) + ';bin',
        '--add-binary', str(a.node.resolve()) + ';bin']
probe = a.ffmpeg.resolve().with_name('ffprobe.exe')
if probe.is_file():
    args += ['--add-binary', str(probe) + ';bin']
for module in ('torch', 'scipy', 'librosa', 'matplotlib', 'pandas', 'IPython', 'pytest'):
    args += ['--exclude-module', module]
args += [str(root / 'music_studio/windows_app.py')]
PyInstaller.__main__.run(args)
distribution = a.output.resolve() / 'Blaze' / 'licenses'
distribution.mkdir(parents=True, exist_ok=True)
shutil.copytree(a.decoder_materials / 'licenses', distribution / 'FFmpeg', dirs_exist_ok=True)
for name in ('FFmpeg-LGPL-Corresponding-Sources.zip', 'decoder-manifest.json'):
    shutil.copy2(a.decoder_materials / name, distribution / name)
