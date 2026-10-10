"""Android dependency safety and Termux installer packaging checks."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('blaze_termux', ROOT / 'blaze.py')
b = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = b
spec.loader.exec_module(b)


class TermuxTests(unittest.TestCase):
    def test_missing_android_tools_do_not_download_desktop_binaries(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {'TERMUX_VERSION': 'test'}), \
                patch.object(b, 'LOCAL_BIN_DIR', Path(folder)), \
                patch.object(b.DependencyInstaller, '_command_runs', return_value=False), \
                patch.object(b.DependencyInstaller, '_pip_install') as pip, \
                patch.object(b.urllib.request, 'urlopen') as download:
            self.assertTrue(b.is_android_runtime())
            self.assertFalse(b.DependencyInstaller._ensure_aria2c())
            with self.assertRaises(SystemExit) as stopped:
                b.DependencyInstaller._ensure_ffmpeg()
            self.assertEqual(stopped.exception.code, 1)
            pip.assert_not_called()
            download.assert_not_called()

    def test_termux_tools_on_path_are_used(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {'TERMUX_VERSION': 'test'}), \
                patch.object(b, 'LOCAL_BIN_DIR', Path(folder)), \
                patch.object(b.DependencyInstaller, '_command_runs', return_value=True):
            self.assertTrue(b.DependencyInstaller._ensure_aria2c())
            self.assertTrue(b.DependencyInstaller._ensure_aria2c(private_only=True))

    def test_missing_ffmpeg_stops_startup(self):
        with patch.dict(os.environ, {'TERMUX_VERSION': 'test'}), \
                patch.object(b.DependencyInstaller, '_command_runs', return_value=False), \
                patch.object(b.DependencyInstaller, '_ensure_local_bin_in_path'), \
                patch.object(b.DependencyInstaller, '_ensure_ytdlp'), \
                patch.object(b.DependencyInstaller, '_ensure_aria2c') as aria:
            with self.assertRaises(SystemExit):
                b.DependencyInstaller.ensure_all()
            aria.assert_not_called()

    def test_archive_has_canonical_source_and_license(self):
        with zipfile.ZipFile(ROOT / 'downloads/Blaze-Termux-Installer.zip') as archive:
            prefix = 'Blaze-Termux-Installer/'
            self.assertEqual(archive.read(prefix + 'blaze.py'),
                             (ROOT / 'blaze.py').read_bytes().replace(b'\r\n', b'\n'))
            for name in ('Install-Blaze.sh', 'README.txt', 'LICENSE.txt', 'THIRD-PARTY-NOTICES.md'):
                self.assertIn(prefix + name, archive.namelist())

    @unittest.skipUnless(sys.platform == 'linux' and shutil.which('bash'), 'Linux Bash required')
    def test_installer_rejects_non_termux_before_changing_home(self):
        with tempfile.TemporaryDirectory() as folder:
            env = os.environ.copy()
            env.pop('TERMUX_VERSION', None)
            env['HOME'] = folder
            script = ROOT / 'installers/termux-installer/Install-Blaze.sh'
            subprocess.run(['bash', '-n', str(script)], check=True)
            result = subprocess.run(['bash', str(script)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('inside Termux', result.stderr)
            self.assertFalse((Path(folder) / 'Blaze').exists())


if __name__ == '__main__':
    unittest.main()
