"""Offline desktop catalogue/process/cache contracts; no provider access."""
from pathlib import Path
import json
import http.client
import importlib.util
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio import discovery as d  # noqa: E402

VIDEO, OTHER = 'abcdefghijk', 'lmnopqrstuv'


def recording(identity=VIDEO, title='A recording', kind='song'):
    return d.canonical_item({'id': identity, 'kind': kind, 'title': title, 'creator': 'An artist',
                             'url': f'https://www.youtube.com/watch?v={identity}', 'durationMs': 180000})


class DesktopDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = d.Discovery(self.root, self.root / 'bin', '/usr/bin/ffmpeg')

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def wait(self, response):
        identity = response['requestId']
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = self.service.status(identity)
            if result['status'] != 'pending':
                return result
            time.sleep(.01)
        self.fail('Worker did not settle')

    def test_canonicalization_rejects_arbitrary_targets_and_normalizes_watch(self):
        value = recording()
        self.assertEqual(value['url'], f'https://www.youtube.com/watch?v={VIDEO}')
        self.assertRaises(ValueError, d.canonical_item, {'id': 'bad', 'kind': 'video', 'title': 'Bad', 'url': 'http://127.0.0.1'})
        self.assertEqual(d._https('https://i.ytimg.com.evil.test/x', d._IMAGES), '')
        self.assertEqual(d._https('https://user@i.ytimg.com/x', d._IMAGES), '')
        self.assertEqual(d._https('https://i.ytimg.com:443/x', d._IMAGES), '')

    def test_search_scope_encoded_bounded_and_metadata_does_not_prepare(self):
        with patch.object(self.service, '_query', return_value=[recording()]) as query:
            result = self.wait(self.service.request({'action': 'search', 'query': 'hello & world', 'filter': 'all', 'limit': 24}))
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(query.call_args.args[1], 'ytsearch24:hello & world')
        self.assertEqual(query.call_args.args[2:], ('all', 24))
        self.assertTrue(result['items'][0]['thumbnail'].startswith('/api/discovery-image?id='))
        self.assertEqual(list(self.service.cache_directory.iterdir()), [])
        self.assertRaises(ValueError, self.service.request, {'action': 'search', 'query': 'a', 'limit': 61})
        self.assertRaises(ValueError, self.service.request, {'action': 'search', 'query': 'bad\nquery'})

    def test_exact_cache_key_and_failure_retry(self):
        with patch.object(self.service, '_query', return_value=[recording()]) as query:
            self.wait(self.service.request({'action': 'search', 'query': 'Music', 'filter': 'all'}))
            self.wait(self.service.request({'action': 'search', 'query': 'Music', 'filter': 'all'}))
            self.wait(self.service.request({'action': 'search', 'query': 'Music', 'filter': 'videos'}))
            self.assertEqual(query.call_count, 2)
        with patch.object(self.service, '_query', side_effect=RuntimeError('secret signed provider URL')):
            result = self.wait(self.service.request({'action': 'search', 'query': 'failure'}))
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('secret', result['error'])
        with patch.object(self.service, '_query', return_value=[recording()]) as query:
            self.wait(self.service.request({'action': 'search', 'query': 'failure'}))
            query.assert_called_once()

    def test_recommendations_mix_seeds_filter_recent_and_diversify(self):
        public = self.service._public(recording())
        self.service.listened({'item': public, 'seconds': 11})
        extra = recording(OTHER, 'A new song')
        with patch.object(self.service, '_query', return_value=[recording(), extra]) as query:
            result = self.wait(self.service.request({'action': 'recommend', 'lane': 'music'}))
        self.assertEqual([row['id'] for row in result['items']], [OTHER])
        self.assertGreaterEqual(query.call_count, 2)
        self.assertIn('An+artist+songs', query.call_args_list[0].args[1])
        self.assertNotIn(VIDEO, query.call_args_list[0].args[1])

    def test_history_only_issued_active_listening_and_persists_canonical_thumbnail(self):
        public = self.service._public(recording())
        forged = dict(public, title='Forged title', creator='Forged artist')
        self.service.listened({'item': forged, 'seconds': 20})
        saved = json.loads(self.service.profile_path.read_text())
        self.assertEqual(saved[0]['title'], 'A recording')
        self.assertTrue(saved[0]['thumbnail'].startswith('https://i.ytimg.com/'))
        self.assertRaises(ValueError, self.service.listened, {'item': recording(OTHER), 'seconds': 20})
        self.assertRaises(ValueError, self.service.listened, {'item': public, 'seconds': 1})
        self.assertRaises(ValueError, self.service.listened, {'item': public, 'seconds': float('nan')})
        self.service.reset()
        self.assertEqual(self.service.history(), [])
        self.assertFalse(self.service.profile_path.exists())

    def test_reset_rejects_late_listening_without_invalidating_sibling_results(self):
        first = self.service._public(recording())
        second = self.service._public(recording(OTHER))
        self.service.listened({'item': first, 'seconds': 15})
        self.service.listened({'item': second, 'seconds': 15})
        self.assertEqual(len(self.service.history()), 2)
        self.service.reset()
        self.assertRaises(ValueError, self.service.listened, {'item': first, 'seconds': 15})
        self.assertRaises(ValueError, self.service.listened, {'item': second, 'seconds': 15})
        self.assertEqual(self.service.history(), [])
        self.assertFalse(self.service.profile_path.exists())
        fresh = self.service._public(recording())
        self.service.listened({'item': fresh, 'seconds': 15})
        self.assertEqual(len(self.service.history()), 1)

    def test_cancel_blocks_late_result_and_playback_worker_independent_of_metadata(self):
        started = threading.Event()
        release = threading.Event()
        def blocked(_job, *_args):
            started.set()
            release.wait(2)
            return [recording()]
        with patch.object(self.service, '_query', side_effect=blocked):
            first = self.service.request({'action': 'search', 'query': 'one'})
            self.assertTrue(started.wait(1))
            second = self.service.request({'action': 'search', 'query': 'two'})
            self.service._public(recording())
            destination = self.service.cache_directory / (VIDEO + '-audio.m4a')
            destination.write_bytes(b'cached playable fixture')
            result = self.wait(self.service.prepare({'item': recording()}))
            self.assertEqual(result['status'], 'ready')
            self.service.cancel(first['requestId'])
            self.service.cancel(second['requestId'])
            release.set()
        self.assertEqual(self.service.status(first['requestId'])['status'], 'cancelled')

    def test_prepare_explicit_only_cached_path_private_and_select_ready(self):
        item = recording()
        self.assertRaises(ValueError, self.service.prepare, {'item': item})
        self.service._public(item)
        self.assertRaises(ValueError, self.service.select, 'unknown')
        def prepare(_job, arguments, **kwargs):
            self.assertIn('--no-write-info-json', arguments)
            self.assertIn('--max-filesize', arguments)
            self.assertEqual(arguments[-1], item['url'])
            self.assertEqual(kwargs['seconds'], 120)
            (kwargs['workspace'] / 'selected.m4a').write_bytes(b'audio fixture')
            return b''
        with patch.object(self.service, '_command', side_effect=prepare):
            response = self.service.prepare({'item': item})
            result = self.wait(response)
        self.assertEqual(result['status'], 'ready')
        self.assertNotIn('path', result)
        path, selected = self.service.select(response['requestId'])
        self.assertEqual(path.read_bytes(), b'audio fixture')
        self.assertEqual(selected['id'], VIDEO)
        self.assertEqual(self.service.pinned, path)
        self.assertEqual(len(list(self.service.cache_directory.iterdir())), 1)

    def test_failed_or_cancelled_prepare_cleans_incomplete_files(self):
        self.service._public(recording())
        def fail(_job, _args, **kwargs):
            (kwargs['workspace'] / 'selected.m4a').write_bytes(b'partial')
            raise RuntimeError('signed secret media URL')
        with patch.object(self.service, '_command', side_effect=fail):
            result = self.wait(self.service.prepare({'item': recording()}))
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('secret', result['error'])
        self.assertEqual(list(self.service.cache_directory.iterdir()), [])

    def test_cache_pruning_reserves_pinned_size_and_preserves_newest(self):
        paths = []
        for number in range(3):
            path = self.service.cache_directory / (str(number) + '.m4a')
            path.write_bytes(b'1234')
            paths.append(path)
        self.service.pinned = paths[0]
        with patch.object(d, 'MAX_CACHE', 10):
            self.service._prune()
        self.assertTrue(paths[0].exists())
        self.assertLessEqual(sum(p.stat().st_size for p in self.service.cache_directory.iterdir()), 10)
        self.assertEqual(len(list(self.service.cache_directory.iterdir())), 2)

    def test_images_require_opaque_known_id_and_redirect_allowlist(self):
        self.assertRaises(ValueError, self.service.image, 'https://127.0.0.1/internal')
        redirect = d.ImageRedirects()
        self.assertRaises(ValueError, redirect.redirect_request, None, None, 302, '', {}, 'http://127.0.0.1/private')
        self.assertRaises(ValueError, redirect.redirect_request, None, None, 302, '', {}, 'https://i.ytimg.com.evil.test/private')

    def test_metadata_command_flat_only_and_never_downloads(self):
        job = {'cancel': threading.Event()}
        with patch.object(self.service, '_command', return_value=json.dumps({'_type': 'playlist', 'entries': [
                {'id': VIDEO, 'title': 'One', 'duration': 123}]}).encode()) as command:
            rows = self.service._query(job, 'ytsearch24:test', 'videos', 24)
        args = command.call_args.args[1]
        self.assertIn('--flat-playlist', args)
        self.assertIn('--skip-download', args)
        self.assertIn('--dump-single-json', args)
        self.assertEqual(rows[0]['id'], VIDEO)

    def test_requests_are_bounded_and_cache_history_not_arbitrary_payload(self):
        release = threading.Event()
        def block(job):
            release.wait(1)
            self.service._check(job)
            return {'items': []}
        requests = [self.service._new('metadata', block) for _ in range(3)]
        self.assertRaises(ValueError, self.service._new, 'metadata', block)
        for response in requests:
            self.service.cancel(response['requestId'])
        release.set()
        self.assertTrue(all(self.service.status(row['requestId'])['status'] == 'cancelled' for row in requests))


@unittest.skipUnless(importlib.util.find_spec('onnxruntime') and importlib.util.find_spec('numpy'),
                     'HTTP integration requires the existing desktop NumPy/ONNX Runtime environment')
class DesktopDiscoveryHTTPTests(unittest.TestCase):
    def setUp(self):
        from music_studio.server import Studio, create_server
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.studio = Studio(self.root, '/usr/bin/ffmpeg')
        self.service = self.studio.discovery = d.Discovery(self.root, self.root / 'bin', '/usr/bin/ffmpeg')
        self.server = create_server(self.studio)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.item = recording(kind='video')
        self.public = self.service._public(self.item)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.studio.close()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None, method=None, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        request_headers = {'X-Blaze-Token': self.studio.token} if token else {}
        request_headers.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            request_headers['Content-Type'] = 'application/json'
        connection.request(method or ('POST' if body is not None else 'GET'), path, data, request_headers)
        response = connection.getresponse()
        value = response.read()
        result = response.status, dict(response.getheaders()), value
        connection.close()
        return result

    def ready(self):
        def prepare(_job, _args, **kwargs):
            (kwargs['workspace'] / 'selected.mp4').write_bytes(b'0123456789abcdef')
            return b''
        with patch.object(self.service, '_command', side_effect=prepare):
            response = self.service.prepare({'item': self.public, 'mode': 'video'})
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if self.service.status(response['requestId'])['status'] != 'pending':
                    break
                time.sleep(.01)
        self.assertEqual(self.service.status(response['requestId'])['status'], 'ready')
        return response['requestId']

    def test_routes_require_token_and_exact_host_origin(self):
        self.assertEqual(self.request('/api/discovery-history', token=False)[0], 403)
        self.assertEqual(self.request('/api/discovery-history', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/discovery-history', headers={'Origin': 'https://evil.test'})[0], 403)
        self.assertEqual(self.request('/api/discovery-history')[0], 200)
        self.assertEqual(self.request('/api/discovery', {'action': 'search', 'query': 'x'}, token=False)[0], 403)

    def test_selection_uses_single_media_trusted_kind_revision_mime_and_range(self):
        identity = self.ready()
        status, _headers, body = self.request('/api/discovery-select', {'requestId': identity})
        self.assertEqual(status, 200)
        selected = json.loads(body)
        self.assertEqual(selected['name'], 'A recording')
        self.assertEqual(selected['mediaKind'], 'video')
        self.assertNotIn(str(self.root), body.decode())
        first = json.loads(self.request('/api/state')[2])
        self.assertEqual(first['sourceRevision'], 1)
        self.assertEqual(first['discoveryItem']['id'], VIDEO)
        self.assertEqual(first['mediaKind'], 'video')
        self.assertEqual(self.request('/media?sourceRevision=1')[0], 200)
        self.request('/api/discovery-select', {'requestId': identity})
        self.assertEqual(json.loads(self.request('/api/state')[2])['sourceRevision'], 2)
        self.assertEqual(self.request('/media?sourceRevision=1')[0], 409)
        self.assertEqual(self.request('/media?sourceRevision=2')[0], 200)
        status, headers, data = self.request('/media', headers={'Range': 'bytes=4-7'})
        self.assertEqual(status, 206)
        self.assertEqual(headers['Content-Type'], 'video/mp4')
        self.assertEqual(headers['Content-Range'], 'bytes 4-7/16')
        self.assertEqual(data, b'4567')
        self.assertEqual(self.request('/media', token=False)[0], 403)
        self.assertEqual(self.request('/media', headers={'Range': 'bytes=99-'})[0], 416)

    def test_arbitrary_items_paths_and_image_urls_cannot_be_selected_or_fetched(self):
        invalid = dict(self.public, id=OTHER, url='file:///etc/passwd')
        self.assertEqual(self.request('/api/discovery-prepare', {'item': invalid})[0], 400)
        self.assertEqual(self.request('/api/discovery-select', {'requestId': '/etc/passwd'})[0], 400)
        with patch('music_studio.discovery.build_opener') as opener:
            self.assertEqual(self.request('/api/discovery-image?id=https://127.0.0.1/private')[0], 400)
            opener.assert_not_called()
        self.assertEqual(self.request('/api/discovery', ['bad body'])[0], 400)
        self.assertEqual(self.request('/api/discovery-image?id=bad', method='POST', body={})[0], 404)

    def test_import_clears_catalogue_metadata_and_changes_source_revision(self):
        self.request('/api/discovery-select', {'requestId': self.ready()})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request('POST', '/api/import', b'RIFFfixture',
                           {'X-Blaze-Token': self.studio.token, 'X-File-Name': 'same-title.wav'})
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        response.read(); connection.close()
        state = json.loads(self.request('/api/state')[2])
        self.assertIsNone(state['discoveryItem'])
        self.assertEqual(state['sourceRevision'], 2)
        self.assertEqual(state['mediaKind'], 'audio')
        self.assertEqual(self.request('/media')[1]['Content-Type'], 'audio/x-wav')

    def test_history_endpoint_preserves_profile_privately_and_reset_removes_it(self):
        self.assertEqual(self.request('/api/discovery-listened', {'item': self.public, 'seconds': 15})[0], 200)
        history = json.loads(self.request('/api/discovery-history')[2])['items']
        self.assertEqual(history[0]['id'], VIDEO)
        self.assertNotIn('https://i.ytimg.com', json.dumps(history))
        self.assertEqual(self.request('/api/discovery-reset', {})[0], 200)
        self.assertEqual(json.loads(self.request('/api/discovery-history')[2])['items'], [])
        self.assertFalse(self.service.profile_path.exists())


if __name__ == '__main__':
    unittest.main()
