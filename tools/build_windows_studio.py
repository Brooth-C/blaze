"""Build the portable Windows Studio from installed, pinned build dependencies."""
from pathlib import Path
import argparse
import shutil
import PyInstaller.__main__

p = argparse.ArgumentParser()
p.add_argument('--ffmpeg', required=True, type=Path)
p.add_argument('--ytdlp', required=True, type=Path)
p.add_argument('--node', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
p.add_argument('--work', required=True, type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
shutil.copy2(root / 'docs/assets/blaze-logo.png', root / 'music_studio/web/blaze-logo.png')
a.work.mkdir(parents=True, exist_ok=True)
# A fixed decoder name keeps the executable independent of the build machine.
decoder = a.work.resolve() / 'decoder' / 'ffmpeg.exe'
decoder.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(a.ffmpeg.resolve(), decoder)
args = ['--noconfirm', '--clean', '--windowed', '--onedir', '--name', 'Blaze',
        '--distpath', str(a.output.resolve()), '--workpath', str(a.work.resolve() / 'pyinstaller'),
        '--specpath', str(a.work.resolve()), '--paths', str(root),
        '--add-data', str(root / 'music_studio/web') + ';music_studio/web',
        '--add-data', str(root / 'music_studio/models') + ';music_studio/models',
        '--add-binary', str(decoder) + ';bin',
        '--add-binary', str(a.ytdlp.resolve()) + ';bin',
        '--add-binary', str(a.node.resolve()) + ';bin']
for module in ('torch', 'scipy', 'librosa', 'matplotlib', 'pandas', 'IPython', 'pytest'):
    args += ['--exclude-module', module]
args += [str(root / 'music_studio/windows_app.py')]
PyInstaller.__main__.run(args)
