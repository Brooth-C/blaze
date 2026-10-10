"""Build reproducible installer ZIPs from the canonical application; --check detects drift."""
import argparse
import hashlib
import io
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_bytes(path):
    """Keep text archive contents identical across Git checkout line endings."""
    return path.read_bytes().replace(b'\r\n', b'\n')


def package(check=False):
    source = source_bytes(ROOT / 'blaze.py')
    app_name = 'blaze.py'
    downloads = ROOT / 'downloads'
    if not check:
        downloads.mkdir(exist_ok=True)
    for platform, scripts in (('Windows', ['Install-Blaze.bat', 'Install-Blaze.ps1']),
                              ('Mac', ['Install-Blaze.command']),
                              ('Linux', ['Install-Blaze.sh'])):
        directory = ROOT / {'Windows': 'installers/windows-installer', 'Mac': 'installers/macos-installer',
                            'Linux': 'installers/linux-installer'}[platform]
        copy = directory / app_name
        if check:
            if source_bytes(copy) != source:
                raise SystemExit(f'{copy.name} differs from blaze.py')
        else:
            copy.write_bytes(source)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in [app_name, 'README.txt', 'LICENSE.txt', 'THIRD-PARTY-NOTICES.md'] + scripts:
                info = zipfile.ZipInfo(f'Blaze-{platform}-Installer/{name}', date_time=(2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                permissions = 0o755 if name.endswith(('.command', '.sh')) else 0o644
                info.external_attr = (stat.S_IFREG | permissions) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                origin = ROOT if name in ('LICENSE.txt', 'THIRD-PARTY-NOTICES.md') else directory
                archive.writestr(info, source_bytes(origin / name), compresslevel=9)
        content = buffer.getvalue()
        output = downloads / f'Blaze-{platform}-Installer.zip'
        if check:
            if output.read_bytes() != content:
                raise SystemExit(f'{output.name} is out of date; run python tools/package_installers.py')
        else:
            output.write_bytes(content)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if archive.testzip() is not None:
                raise SystemExit(f'{output.name} failed integrity verification')
        print(f'{output.name}: {len(content)} bytes, SHA256 {hashlib.sha256(content).hexdigest()}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    package(parser.parse_args().check)
