"""Mac presentation isolation and native-selected file ownership boundaries."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio, create_server


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.studio = Studio(self.root / 'data', 'ffmpeg')
        self.addCleanup(self.studio.close)

    def request(self, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        headers = {'X-Blaze-Token': self.studio.token}
        connection.request('GET' if body is None else 'POST', path,
                           None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        return response.status, response.read().decode()

    def serve(self):
        self.server = create_server(self.studio)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def test_mac_assets_are_opted_in_by_the_native_host(self):
        self.serve()
        status, html = self.request('/?presentation=mac')
        self.assertEqual(status, 200)
        self.assertIn('data-presentation="desktop"', html)
        self.assertNotIn('href="/mac.css"', html)
        self.assertNotIn('src="/mac.js"', html)
        self.assertNotIn('%%', html)
        self.assertEqual(self.request('/mac.css')[0], 404)
        self.studio.presentation = 'mac'
        status, html = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('data-presentation="mac"', html)
        self.assertIn('href="/mac.css"', html)
        self.assertIn('src="/mac.js"', html)
        self.assertEqual(self.request('/mac.css')[0], 200)
        self.assertEqual(self.request('/mac.js')[0], 200)

    def test_native_selection_is_not_exposed_as_a_path_http_api(self):
        self.serve()
        source = self.root / 'private.wav'
        source.write_bytes(b'local fixture')
        for path in ('/api/open-local-file', '/api/open_local_file'):
            self.assertEqual(self.request(path, {'path': str(source)})[0], 404)
        self.assertIsNone(self.studio.source)

    def test_native_selection_preserves_user_files_and_changes_revision(self):
        incoming = self.studio.incoming / 'previous.wav'
        incoming.write_bytes(b'temporary upload')
        self.studio.source, self.studio.imported = incoming, True
        source = self.root / 'Selected recording.MP4'
        source.write_bytes(b'local fixture')
        self.studio.state.update(result={'old': True}, discoveryItem={'id': 'old'})
        result = self.studio.open_local_file(source)
        self.assertFalse(incoming.exists())
        self.assertEqual(self.studio.source, source)
        self.assertEqual(result, {'name': source.name, 'sourceRevision': 1, 'mediaKind': 'video'})
        self.assertIsNone(self.studio.state['result'])
        self.assertIsNone(self.studio.state['discoveryItem'])
        self.studio.close()
        self.assertTrue(source.exists())

    def test_invalid_or_busy_selection_keeps_the_existing_source(self):
        source = self.root / 'original.wav'
        source.write_bytes(b'local fixture')
        self.studio.open_local_file(source)
        empty = self.root / 'empty.wav'
        empty.touch()
        for selected in (self.root / 'missing.wav', self.root, empty, None):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.studio.open_local_file(selected)
            self.assertEqual(self.studio.source, source)
            self.assertEqual(self.studio.source_revision, 1)
        self.studio.state['busy'] = True
        other = self.root / 'other.wav'
        other.write_bytes(b'new fixture')
        with self.assertRaisesRegex(ValueError, 'analysis'):
            self.studio.open_local_file(other)
        self.assertEqual(self.studio.source, source)
        self.assertEqual(self.studio.source_revision, 1)


if __name__ == '__main__':
    unittest.main()
