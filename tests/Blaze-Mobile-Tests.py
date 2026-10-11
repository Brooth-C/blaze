"""Local APK backend tests: download selection, cancellation and playlist safety."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
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
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'MobileYDL') as engine:
            with self.assertRaises(b.DownloadCancelled):
                b.download('https://example.com/video', 'video', folder, callback)
            engine.assert_not_called()

    def test_playlist_rejected_before_download(self):
        callback = Mock()
        callback.isCancelled.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'MobileYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'_type': 'playlist'}
            with self.assertRaises(ValueError):
                b.download('https://example.com/list', 'video', folder, callback)
            client.process_info.assert_not_called()

    def test_complete_file_returned_and_progress_can_cancel(self):
        callback = Mock()
        callback.isCancelled.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'MobileYDL') as engine:
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
        with tempfile.TemporaryDirectory() as folder, patch.object(b, 'MobileYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'title': 'Video in Ogg', 'vcodec': 'theora', 'acodec': 'vorbis'}
            with self.assertRaises(ValueError):
                b.download('https://example.com/video.ogg', 'audio', folder, callback)
            client.process_info.assert_not_called()

    def test_playlist_expansion_deduplicates_and_never_downloads(self):
        callback=Mock();callback.isCancelled.return_value=False
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'MobileYDL') as engine:
            client=engine.return_value.__enter__.return_value
            client.extract_info.return_value={'_type':'playlist','entries':[None,{'url':'https://example.com/a','title':'A'},{'url':'https://example.com/a'},{'url':'file:///private'},{'url':'https://example.com/b'}]}
            result=json.loads(b.download('https://example.com/list','video',folder,callback,'{"playlist":true}'))
            self.assertEqual([e['url'] for e in result['playlist_entries']],['https://example.com/a','https://example.com/b'])
            client.process_info.assert_not_called()

    def test_playlist_bound_is_enforced_before_download(self):
        callback=Mock();callback.isCancelled.return_value=False
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'MobileYDL') as engine:
            client=engine.return_value.__enter__.return_value
            client.extract_info.return_value={'_type':'playlist','entries':[{'url':f'https://example.com/{i}'} for i in range(201)]}
            with self.assertRaises(ValueError):b.download('https://example.com/list','video',folder,callback,'{"playlist":true}')
            client.process_info.assert_not_called()

    def test_conversion_requires_bundled_tool_before_network(self):
        callback=Mock();callback.isCancelled.return_value=False
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'MobileYDL') as engine:
            with self.assertRaises(ValueError):b.download('https://example.com/audio','audio',folder,callback,'{"audio":"mp3"}')
            engine.assert_not_called()
        self.assertEqual(b._sessions,{})

    def test_native_process_cancellation_reaps_child(self):
        callback=Mock();callback.isCancelled.return_value=False
        session=b.Session(callback);token='process-fixture';b._sessions[token]=session
        context=b._session.set(session)
        try:
            with b.CancellablePopen([sys.executable,'-c','import time; time.sleep(30)'],stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
                b.cancel(token);process.communicate(timeout=5)
                self.assertIsNotNone(process.poll())
        finally:
            b._session.reset(context);b._sessions.pop(token,None)

    def test_cancellation_during_extraction_prevents_file_write(self):
        callback=Mock();callback.isCancelled.return_value=False
        with tempfile.TemporaryDirectory() as folder,patch.object(b,'MobileYDL') as engine:
            client=engine.return_value.__enter__.return_value
            def extracted(*args,**kwargs):
                b.cancel('extract-fixture');return {'title':'Item','vcodec':'h264','acodec':'aac'}
            client.extract_info.side_effect=extracted
            with self.assertRaises(b.DownloadCancelled):b.download('https://example.com/video','video',folder,callback,token='extract-fixture')
            client.process_info.assert_not_called()


if __name__ == '__main__':
    unittest.main()

