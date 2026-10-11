"""Local APK backend tests: download selection, cancellation and playlist safety."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mobile', ROOT / 'android/app/src/main/python/blaze_mobile.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class MobileTests(unittest.TestCase):
    def test_rejects_unsupported_and_credential_urls(self):
        for url in ('http://example.com/a', 'file:///etc/passwd', 'https://me:pass@example.com/a', 'bad'):
            with self.assertRaises(ValueError):
                b.validate_url(url)

    def test_cancelled_request_never_starts(self):
        callback = Mock()
        callback.isCancelled.return_value = True
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'YoutubeDL') as engine:
            with self.assertRaises(b.DownloadCancelled):
                b.download('https://example.com/video', 'video', folder, callback)
            engine.assert_not_called()

    def test_playlist_rejected_before_download(self):
        callback = Mock()
        callback.isCancelled.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'YoutubeDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'_type': 'playlist'}
            with self.assertRaises(ValueError):
                b.download('https://example.com/list', 'video', folder, callback)
            client.process_info.assert_not_called()

    def test_complete_file_returned_and_progress_can_cancel(self):
        callback = Mock()
        callback.isCancelled.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'YoutubeDL') as engine:
            path = Path(folder) / 'example.mp4'
            path.write_bytes(b'test')
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'title': 'Example', 'vcodec': 'h264', 'acodec': 'aac'}
            client.prepare_filename.return_value = str(path)
            result = json.loads(b.download('https://example.com/video', 'video', folder, callback))
            self.assertEqual(result['path'], str(path.resolve()))
            options = engine.call_args.args[0]
            self.assertEqual(options['postprocessors'], [])
            callback.isCancelled.return_value = True
            with self.assertRaises(b.DownloadCancelled):
                options['progress_hooks'][0]({'status': 'downloading'})

    def test_audio_mode_rejects_video_before_saving(self):
        callback = Mock()
        callback.isCancelled.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'YoutubeDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'title': 'Video in Ogg', 'vcodec': 'theora', 'acodec': 'vorbis'}
            with self.assertRaises(ValueError):
                b.download('https://example.com/video.ogg', 'audio', folder, callback)
            client.process_info.assert_not_called()


if __name__ == '__main__':
    unittest.main()

