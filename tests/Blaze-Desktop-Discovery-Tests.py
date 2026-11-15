"""Offline desktop catalogue/process/cache contracts; no provider access."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import http.client
import importlib.util
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
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

    def test_search_metadata_survives_cache_canonicalization_without_inventing_values(self):
        value = d.normalize({'id': VIDEO, 'title': 'Piano', 'view_count': 12345,
                             'upload_date': '20261101', 'description': 'A live session'})
        restored = d.canonical_item(value)
        for key in ('viewCount', 'publishedDate', 'description'):
            self.assertEqual(restored[key], value[key])
        for invalid in (True, -1, 'many', 10**16):
            bare = d.normalize({'id': VIDEO, 'title': 'Piano', 'view_count': invalid})
            self.assertNotIn('viewCount', bare)
            self.assertNotIn('publishedDate', bare)
            self.assertNotIn('description', bare)

    def test_catalogue_reopens_from_disk_without_running_provider_again(self):
        with patch.object(self.service, '_query', return_value=[recording()]) as query:
            first = self.wait(self.service.request({'action': 'search', 'query': 'cached music'}))
            self.assertEqual(query.call_count, 1)
        self.service.close()
        self.service = d.Discovery(self.root, self.root / 'bin', '/usr/bin/ffmpeg')
        with patch.object(self.service, '_query', side_effect=AssertionError('Unexpected provider fetch')):
            again = self.wait(self.service.request({'action': 'search', 'query': 'cached music'}))
        self.assertEqual(again['status'], 'ready')
        self.assertEqual(again['items'][0]['id'], first['items'][0]['id'])
        self.service.reset()
        self.assertEqual(list(self.service.directory.glob('catalogue-*.json')), [])

    def test_mac_image_proxy_loads_roots_and_reopens_artwork_offline(self):
        item = self.service._public(recording())
        identity = item['thumbnail'].split('id=')[1]
        response = MagicMock()
        response.headers.get_content_type.return_value = 'image/jpeg'
        response.read.return_value = b'jpeg-fixture'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        context = MagicMock()
        with patch.object(d.sys, 'platform', 'darwin'), patch.dict(d.os.environ, {'SSL_CERT_FILE': ''}), \
                patch.object(d.ssl, 'create_default_context', return_value=context), \
                patch.object(d.subprocess, 'run', return_value=type('Roots', (), {'stdout': b'PEM roots'})()), \
                patch.object(d, 'build_opener', return_value=opener):
            self.assertEqual(self.service.image(identity), (b'jpeg-fixture', 'image/jpeg'))

        context.load_verify_locations.assert_called_once_with(cadata='PEM roots')
        self.service.close()
        self.service = d.Discovery(self.root, self.root / 'bin', '/usr/bin/ffmpeg')
        identity = self.service._public(recording())['thumbnail'].split('id=')[1]
        with patch.object(d, 'build_opener', side_effect=AssertionError('Unexpected image fetch')):
            self.assertEqual(self.service.image(identity), (b'jpeg-fixture', 'image/jpeg'))
        with patch.object(Path, 'open', side_effect=AssertionError('Disk cache was not promoted to memory')):
            self.assertEqual(self.service.image(identity), (b'jpeg-fixture', 'image/jpeg'))

    def test_mac_matching_image_requests_share_success_and_failure_without_holding_lock(self):
        self.service.verify_playback = True
        identity = self.service._public(recording())['thumbnail'].split('id=')[1]
        for fails in (False, True):
            with self.subTest(fails=fails):
                entered, joined, release = threading.Event(), threading.Event(), threading.Event()
                pending = d.Future()
                wait = pending.result

                def result(*args, **kwargs):
                    joined.set()
                    return wait(*args, **kwargs)

                pending.result = result

                def load(value):
                    self.assertEqual(value, identity)
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError('Image test did not release')
                    if fails:
                        raise ValueError('Unavailable artwork')
                    return b'jpeg-fixture', 'image/jpeg'

                with patch.object(d, 'Future', return_value=pending), \
                        patch.object(self.service, '_load_image', side_effect=load) as fetch, \
                        ThreadPoolExecutor(max_workers=2) as workers:
                    first = workers.submit(self.service.image, identity)
                    self.assertTrue(entered.wait(2))
                    second = workers.submit(self.service.image, identity)
                    try:
                        self.assertTrue(joined.wait(2))
                        self.assertTrue(self.service.lock.acquire(timeout=.5))
                        self.service.lock.release()
                    finally:
                        release.set()
                    for request in (first, second):
                        if fails:
                            with self.assertRaisesRegex(ValueError, 'Unavailable artwork'):
                                request.result(timeout=2)
                        else:
                            self.assertEqual(request.result(timeout=2), (b'jpeg-fixture', 'image/jpeg'))
                    self.assertEqual(fetch.call_count, 1)
                self.assertEqual(self.service.image_requests, {})
        with patch.object(self.service, '_load_image', return_value=(b'retry', 'image/jpeg')):
            self.assertEqual(self.service.image(identity), (b'retry', 'image/jpeg'))

    def test_expired_video_artwork_uses_public_static_thumbnail(self):
        item = recording()
        item['thumbnail'] = f'https://i.ytimg.com/vi/{VIDEO}/hqdefault.jpg?expired=1'
        identity = self.service._public(item)['thumbnail'].split('id=')[1]
        response = MagicMock()
        response.__enter__.return_value.headers.get_content_type.return_value = 'image/jpeg'
        response.__enter__.return_value.read.return_value = b'fallback-jpeg'
        opener = MagicMock()
        opener.open.side_effect = [d.HTTPError(item['thumbnail'], 403, 'Expired', {}, None), response]
        with patch.object(d, 'build_opener', return_value=opener):
            self.assertEqual(self.service.image(identity), (b'fallback-jpeg', 'image/jpeg'))
        self.assertEqual(opener.open.call_args_list[1].args[0].full_url, f'https://i.ytimg.com/vi/{VIDEO}/mqdefault.jpg')

    def test_replaying_same_song_reuses_unchanged_recommendation_seeds(self):
        item = self.service._public(recording())
        self.service.listened({'item': item, 'seconds': 11})
        with patch.object(self.service, '_query', return_value=[recording(OTHER, 'New song')]):
            self.assertEqual(self.wait(self.service.request({'action': 'recommend'}))['status'], 'ready')
        self.service.listened({'item': item, 'seconds': 11})
        with patch.object(self.service, '_query', side_effect=AssertionError('Unchanged seeds should use cache')):
            result = self.wait(self.service.request({'action': 'recommend'}))
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['items'][0]['id'], OTHER)

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

    def test_mac_warm_search_returns_ready_without_worker_or_poll(self):
        self.service.verify_playback = True
        body = {'action': 'search', 'query': 'Repeated song', 'filter': 'all', 'limit': 16}
        with patch.object(self.service, '_query', return_value=[recording()]) as provider:
            first = self.wait(self.service.request(body))
            with patch.object(self.service, '_new', side_effect=AssertionError('Warm search queued a worker')):
                again = self.service.request(body)
        self.assertEqual(again['status'], 'ready')
        self.assertNotIn('requestId', again)
        self.assertEqual(again['items'][0]['id'], first['items'][0]['id'])
        self.assertEqual(provider.call_count, 1)

    def test_mac_status_wait_wakes_on_completion_and_cancel(self):
        self.service.verify_playback = True
        release = threading.Event()
        answer = self.service._new('metadata', lambda _job: (release.wait(2) and {'items': []}))
        self.assertTrue(answer['canWait'])
        returned = threading.Event()
        values = []
        waiter = threading.Thread(target=lambda: (values.append(self.service.wait_status(answer['requestId'])), returned.set()))
        waiter.start()
        self.assertFalse(returned.wait(.02), 'Pending wait returned without waiting')
        release.set()
        self.assertTrue(returned.wait(1))
        waiter.join(1)
        self.assertEqual(values[0]['status'], 'ready')

        release.clear()
        second = self.service._new('metadata', lambda _job: (release.wait(2) and {'items': []}))
        try:
            self.service.cancel(second['requestId'])
            self.assertEqual(self.service.wait_status(second['requestId'])['status'], 'cancelled')
        finally:
            release.set()

    def test_mac_root_export_is_reused_and_explicit_ca_is_preserved(self):
        self.service.verify_playback = True
        pem = d.ssl.DER_cert_to_PEM_cert(d.ssl.create_default_context().get_ca_certs(binary_form=True)[0]).encode('ascii')
        result = MagicMock(stdout=pem)
        job = {'cancel': threading.Event()}
        with patch.object(d.sys, 'platform', 'darwin'), patch.dict(d.os.environ, {'SSL_CERT_FILE': ''}), \
                patch.object(d.subprocess, 'run', return_value=result) as export:
            first = self.service._tls_environment(job)
            again = self.service._tls_environment(job)
            self.assertEqual(first['SSL_CERT_FILE'], again['SSL_CERT_FILE'])
            self.assertEqual(Path(first['SSL_CERT_FILE']).read_bytes(), pem)
            self.assertEqual(export.call_count, 1)
            with patch.dict(d.os.environ, {'SSL_CERT_FILE': '/explicit/trust.pem'}):
                self.assertIsNone(self.service._tls_environment(job))
                self.assertEqual(export.call_count, 1)
        self.service.close()
        self.assertFalse(Path(first['SSL_CERT_FILE']).exists())

    def test_mac_bad_root_export_is_not_cached(self):
        self.service.verify_playback = True
        with patch.object(d.sys, 'platform', 'darwin'), patch.dict(d.os.environ, {'SSL_CERT_FILE': ''}), \
                patch.object(d.subprocess, 'run', return_value=MagicMock(stdout=b'not a certificate')):
            self.assertRaises(d.ssl.SSLError, self.service._tls_environment, {'cancel': threading.Event()})
        self.assertIsNone(self.service.tls_file)

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

    def test_mac_rejects_result_with_conflicting_video_id_and_url(self):
        self.service.verify_playback = True
        job = {'cancel': threading.Event()}
        payload = {'_type': 'playlist', 'entries': [
            {'id': VIDEO, 'url': f'https://www.youtube.com/watch?v={OTHER}', 'title': 'Wrong pairing'},
            {'id': OTHER, 'url': f'https://www.youtube.com/watch?v={OTHER}', 'title': 'Correct pairing'}]}
        with patch.object(self.service, '_command', return_value=json.dumps(payload).encode()):
            rows = self.service._query(job, 'ytsearch2:example', 'all', 2)
        self.assertEqual([(row['id'], row['title']) for row in rows], [(OTHER, 'Correct pairing')])

    def test_mac_verifies_download_identity_and_ignores_legacy_cache(self):
        self.service.verify_playback = True
        item = self.service._public(recording())
        legacy = self.service.cache_directory / (VIDEO + '-audio.m4a')
        legacy.write_bytes(b'unverified old media')

        def wrong(_job, arguments, **kwargs):
            self.assertIn('after_move:%(id)s', arguments)
            self.assertIn('--no-simulate', arguments)
            (kwargs['workspace'] / 'selected.m4a').write_bytes(b'wrong media')
            return (OTHER + '\n').encode()

        with patch.object(self.service, '_command', side_effect=wrong):
            failed = self.wait(self.service.prepare({'item': item}))
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse(any(self.service.cache_directory.glob('verified-v1-*')))

        def correct(_job, arguments, **kwargs):
            (kwargs['workspace'] / 'selected.m4a').write_bytes(b'correct media')
            return (VIDEO + '\n').encode()

        with patch.object(self.service, '_command', side_effect=correct):
            first = self.service.prepare({'item': item})
            self.assertEqual(self.wait(first)['status'], 'ready')
        path, selected = self.service.select(first['requestId'])
        self.assertEqual(path.read_bytes(), b'correct media')
        self.assertEqual(selected['id'], VIDEO)
        with patch.object(self.service, '_command', side_effect=AssertionError('Verified cache should be reused')):
            second = self.service.prepare({'item': item})
            self.assertEqual(self.wait(second)['status'], 'ready')
        self.assertRaisesRegex(ValueError, 'newer recording', self.service.select, first['requestId'])
        self.assertEqual(self.service.select(second['requestId'])[0], path)

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

    def test_mac_late_selection_cannot_replace_a_new_recording(self):
        self.studio.presentation = 'mac'
        identity = self.ready()
        original = self.root / 'New import.wav'
        original.write_bytes(b'user chose a different recording')
        self.studio.select_source(original, original.name)
        self.assertEqual(self.request('/api/discovery-select', {'requestId': identity, 'sourceRevision': 0})[0], 400)
        self.assertEqual(self.studio.source, original)
        self.assertEqual(self.studio.name, 'New import.wav')
        status, _, raw = self.request('/api/discovery-select', {'requestId': identity, 'sourceRevision': 1})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['sourceRevision'], 2)

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
