"""Appearance stays local and survives app restarts independently of the loopback port."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio

class AppearanceTests(unittest.TestCase):
    def test_default_and_unreadable_preferences_use_system(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Studio(directory, 'ffmpeg').appearance, 'system')
            path = Path(directory) / 'appearance.json'
            for content in ('broken json', '[]', 'null', '{"appearance":"unknown"}'):
                path.write_text(content)
                self.assertEqual(Studio(directory, 'ffmpeg').appearance, 'system')

    def test_each_supported_choice_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = Studio(directory, 'ffmpeg')
            for choice in ('dark', 'light', 'system'):
                studio.set_appearance(choice)
                self.assertEqual(Studio(directory, 'ffmpeg').appearance, choice)
                self.assertFalse((Path(directory) / 'appearance.tmp').exists())

    def test_invalid_choice_preserves_saved_appearance(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = Studio(directory, 'ffmpeg')
            studio.set_appearance('dark')
            for value in ('unknown', '<script>', None, [], {}):
                with self.assertRaises(ValueError):
                    studio.set_appearance(value)
            self.assertEqual(Studio(directory, 'ffmpeg').appearance, 'dark')

if __name__ == '__main__':
    unittest.main()
