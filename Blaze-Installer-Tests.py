"""Install and upgrade the committed ZIP on a disposable Windows/macOS CI runner."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent


@unittest.skipUnless(sys.platform in ('darwin', 'win32'), 'Windows/macOS installer test')
class InstallerTests(unittest.TestCase):
    def test_install_launch_upgrade_and_reject_invalid_source(self):
        platform = 'Windows' if sys.platform == 'win32' else 'Mac'
        root = Path.home() / 'Blaze'
        self.assertFalse(root.exists(), 'Run this test on a disposable clean CI runner')
        with tempfile.TemporaryDirectory(prefix='Blaze setup ') as temporary:
            extracted = Path(temporary)
            with zipfile.ZipFile(PROJECT / 'downloads' / f'Blaze-{platform}-Installer.zip') as archive:
                archive.extractall(extracted)
                for member in archive.infolist():
                    if member.filename.endswith('.command'):
                        (extracted / member.filename).chmod(0o755)
            directory = extracted / f'Blaze-{platform}-Installer'
            source = directory / 'blaze.py'
            original = source.read_bytes()
            version = re.search(rb'^VERSION = "([^"]+)"', original, re.MULTILINE).group(1).decode()
            def install(expect_success=True):
                command = (['powershell.exe', '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(directory / 'Install-Blaze.ps1')]
                           if sys.platform == 'win32' else ['bash', str(directory / 'Install-Blaze.command')])
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=360)
                sys.stdout.buffer.write(result.stdout)
                sys.stdout.buffer.flush()
                self.assertEqual(result.returncode == 0, expect_success)
                if not expect_success:
                    self.assertIn(b'SyntaxError', result.stdout, 'Failure did not reach app validation')
            install()
            application = root / 'App' / 'blaze.py'
            python = root / '.runtime' / 'venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            bin_dir = root / '.runtime' / 'bin'
            environment = os.environ.copy()
            environment['PATH'] = str(bin_dir) + os.pathsep + str(python.parent) + os.pathsep + environment.get('PATH', '')
            check = subprocess.run([str(python), '-c', 'import sys, yt_dlp, rich, mutagen, imageio_ffmpeg; print(sys.prefix)'], check=True, capture_output=True, text=True, env=environment)
            self.assertTrue(Path(check.stdout.strip()).resolve().is_relative_to((root / '.runtime').resolve()))
            self.assertEqual(application.read_bytes(), original)
            launcher = root / ('Start-Blaze.bat' if sys.platform == 'win32' else 'Start-Blaze.command')
            command = (['cmd.exe', '/d', '/c', str(launcher), '--help'] if sys.platform == 'win32'
                       else ['bash', str(launcher), '--help'])
            help_result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment, timeout=30)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn('usage:', help_result.stdout.lower())
            version_result = subprocess.run(command[:-1] + ['--version'], stdin=subprocess.DEVNULL,
                                            capture_output=True, text=True, env=environment, timeout=30)
            self.assertEqual(version_result.returncode, 0, version_result.stderr)
            self.assertIn(version, version_result.stdout)
            sentinels = {root / 'Config' / 'config.json': json.dumps({'workers': 2, 'format': 'flac'}),
                         root / 'Audio' / 'keep.txt': 'existing download',
                         root / 'Reports' / 'keep.txt': 'existing report'}
            for path, content in sentinels.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
            old_launcher = hashlib.sha256(launcher.read_bytes()).hexdigest()
            source.write_text('this is not valid Python !!!', encoding='utf-8')
            install(expect_success=False)
            self.assertEqual(application.read_bytes(), original)
            self.assertEqual(hashlib.sha256(launcher.read_bytes()).hexdigest(), old_launcher)
            source.write_bytes(original)
            install()
            for path, content in sentinels.items():
                self.assertEqual(path.read_text(encoding='utf-8'), content)
            self.assertFalse([path for path in (root / '.runtime').glob('setup*') if path.is_dir()])
            self.assertFalse((root / '.runtime' / 'setup.lock.d').exists())
            for suite in ('Blaze-Regression-Tests.py', 'Blaze-Reliability-Tests.py', 'Blaze-Integration-Tests.py'):
                subprocess.run([str(python), str(PROJECT / suite)], check=True, timeout=180, env=environment)
            # Retain the verified installation for subsequent CI diagnostics.


if __name__ == '__main__':
    unittest.main()
