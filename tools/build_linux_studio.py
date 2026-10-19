"""Package the Linux desktop installer with reviewed models and Node, without training."""
from pathlib import Path
import argparse
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    stage = args.work.resolve() / 'Blaze'
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'music_studio', stage / 'music_studio', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'incoming', 'analyses'))
    for name in ('blaze.py', 'LICENSE.txt', 'THIRD-PARTY-NOTICES.md'):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(args.assets / 'bin', stage / 'bin', dirs_exist_ok=True)
    shutil.copytree(args.assets / 'notices', stage / 'licenses', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'docs/assets/blaze-logo.png', stage / 'blaze-logo.png')
    shutil.copy2(ROOT / 'installers/linux-desktop/Install-Blaze.sh', stage / 'Install-Blaze.sh')
    (stage / 'Install-Blaze.sh').chmod(0o755)
    (stage / 'requirements.txt').write_text('numpy==1.26.4\nonnxruntime==1.20.1\npywebview==6.1\nPillow==11.3.0\nrich==14.2.0\nyt-dlp==2026.8.19\nyt-dlp-ejs==0.8.0\n', encoding='utf-8')
    shutil.copy2(ROOT / 'docs/LINUX-DESKTOP.md', stage / 'README.md')
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / 'Blaze-Linux-x86_64.tar.gz'
    with tarfile.open(destination, 'w:gz') as archive:
        archive.add(stage, arcname='Blaze', filter=lambda entry: None if '__pycache__' in entry.name else entry)
    print(destination)


if __name__ == '__main__':
    main()
