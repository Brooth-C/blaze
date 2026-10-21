"""Offline discovery contracts: bounded metadata, typed identities and playback safety."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / 'android/app/src/main/python'
sys.path.insert(0, str(PYTHON))
spec = importlib.util.spec_from_file_location('discovery', PYTHON / 'blaze_discovery.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
import blaze_mobile as mobile  # noqa: E402

VIDEO = 'abcdefghijk'
OTHER = 'lmnopqrstuv'
CHANNEL = 'UC' + 'a' * 22
PLAYLIST = 'PL' + 'b' * 30
VIDEO_URL = f'https://www.youtube.com/watch?v={VIDEO}'
STREAM = 'https://rr1---sn-test.googlevideo.com/videoplayback?expire=123456789&secret=stream-token'


def callback(cancelled=False):
    value = Mock()
    value.isCancelled.return_value = cancelled
    return value


def item(kind='song'):
    return json.dumps({'id': VIDEO, 'kind': kind, 'url': VIDEO_URL, 'title': 'Recording'})


class DiscoveryTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(d._sessions, {}, 'Discovery operation leaked')
        self.assertEqual(mobile._sessions, {}, 'Stream resolution leaked native session')

    def test_video_identity_is_canonical_and_tracking_is_not_persisted(self):
        result = d.normalize({'id': VIDEO, 'url': f'https://music.youtube.com/watch?v={VIDEO}&list=RDABC&tracking=one',
                              'title': 'A\nrecording', 'channel': 'Creator', 'duration': 42.5})
        self.assertEqual(result['url'], VIDEO_URL)
        self.assertEqual(result['id'], VIDEO)
        self.assertEqual(result['title'], 'A recording')
        self.assertEqual(result['durationMs'], 42500)
        self.assertNotIn('stream', result)

    def test_missing_metadata_remains_unknown_and_bad_image_is_rejected(self):
        result = d.normalize({'id': VIDEO, 'title': 'A', 'duration': float('nan'),
                              'thumbnail': 'https://i.ytimg.com.evil.test/a.jpg'}, 'songs')
        self.assertEqual(result['durationMs'], -1)
        self.assertEqual(result['creator'], '')
        self.assertEqual(result['kind'], 'song')
        self.assertEqual(result['thumbnail'], f'https://i.ytimg.com/vi/{VIDEO}/mqdefault.jpg')

    def test_collections_keep_their_type_and_invalid_ids_cannot_become_watch_urls(self):
        artist = d.normalize({'id': CHANNEL, 'title': 'Artist', 'url': f'https://music.youtube.com/browse/{CHANNEL}'})
        playlist = d.normalize({'id': PLAYLIST, 'title': 'Mix', 'url': f'https://music.youtube.com/playlist?list={PLAYLIST}'})
        self.assertEqual(artist['kind'], 'artist')
        self.assertEqual(artist['url'], f'https://www.youtube.com/channel/{CHANNEL}')
        self.assertEqual(playlist['kind'], 'playlist')
        self.assertIn('/playlist?', playlist['url'])
        short_id = 'PLabcdefghi'
        short = d.normalize({'id': short_id, 'title': 'Short list', 'url': f'https://www.youtube.com/playlist?list={short_id}'})
        self.assertEqual(short['kind'], 'playlist', 'A collection with an 11-character ID is not a video')
        self.assertIsNone(d.normalize({'id': 'arbitrary', 'url': 'https://evil.test/media', 'title': 'Unsafe'}))

    def test_music_renderer_preserves_real_creator_duration_and_art(self):
        renderer = {'playlistItemData': {'videoId': VIDEO}, 'flexColumns': [
            {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [{'text': 'Golden Hour'}]}}},
            {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [
                {'text': 'The Northlights', 'navigationEndpoint': {'browseEndpoint': {'browseId': CHANNEL}}},
                {'text': ' • '}, {'text': '3:42'}]}}}],
            'thumbnail': {'musicThumbnailRenderer': {'thumbnail': {'thumbnails': [
                {'url': 'https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg', 'width': 320}]}}}}
        raw = d.BlazeMusicSearch()._music_reponsive_list_entry(renderer)
        result = d.normalize(raw)
        self.assertEqual(result['title'], 'Golden Hour')
        self.assertEqual(result['creator'], 'The Northlights')
        self.assertEqual(result['durationMs'], 222000)
        self.assertEqual(result['kind'], 'song')
        self.assertEqual(result['thumbnail'], 'https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg')

    def test_music_artist_title_is_not_lost_by_flat_upstream_adapter(self):
        renderer = {'navigationEndpoint': {'browseEndpoint': {'browseId': CHANNEL}}, 'flexColumns': [
            {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [{'text': 'An Artist'}]}}}]}
        result = d.normalize(d.BlazeMusicSearch()._music_reponsive_list_entry(renderer))
        self.assertEqual(result['kind'], 'artist')
        self.assertEqual(result['title'], 'An Artist')

    def test_search_is_flat_bounded_deduplicated_and_never_downloads(self):
        with patch.object(d, 'DiscoveryYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'_type': 'playlist', 'entries': [
                {'id': VIDEO, 'title': 'First'}, {'id': VIDEO, 'title': 'Duplicate'},
                {'id': OTHER, 'title': 'Second'}]}
            result = json.loads(d.search('a term', 'videos', 2, 'search-safe', callback()))
            self.assertEqual(len(result['items']), 1)  # The raw provider prefix is bounded too.
            client.extract_info.assert_called_once_with('ytsearch2:a term', download=False)
            client.process_info.assert_not_called()
            client.download.assert_not_called()
            options = engine.call_args.args[0]
            self.assertEqual(options['playlist_items'], '1:2')
            self.assertEqual(options['postprocessors'], [])
            self.assertTrue(options['skip_download'])
            self.assertFalse(options['cachedir'])

    def test_music_and_artist_scopes_use_selected_catalogues(self):
        with patch.object(d, 'DiscoveryYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'_type': 'playlist', 'entries': []}
            d.search('café keys', 'songs', 20, 'music', callback())
            self.assertEqual(client.extract_info.call_args.args[0], 'https://music.youtube.com/search?q=caf%C3%A9%20keys#songs')
            d.search('pianist', 'artists', 20, 'artist', callback())
            self.assertIn('sp=EgIQAg%3D%3D', client.extract_info.call_args.args[0])

    def test_cancel_before_start_does_not_construct_network_engine(self):
        with patch.object(d, 'DiscoveryYDL') as engine:
            result = json.loads(d.search('query', 'all', 20, 'cancelled', callback(True)))
            self.assertTrue(result['error'])
            engine.assert_not_called()

    def test_cancellation_tokens_are_independent(self):
        first, second = callback(), callback()
        with d._session('first', first) as one, d._session('second', second) as two:
            d.cancel('first')
            with self.assertRaises(d.DiscoveryCancelled):
                one.check()
            two.check()
            self.assertFalse(two.cancelled.is_set())

    def test_search_errors_never_return_signed_url_or_provider_exception(self):
        with patch.object(d, 'DiscoveryYDL') as engine:
            engine.return_value.__enter__.return_value.extract_info.side_effect = RuntimeError('Forbidden ' + STREAM)
            output = d.search('query', 'videos', 20, 'error-safe', callback())
            self.assertNotIn('stream-token', output)
            self.assertNotIn('videoplayback', output)
            self.assertTrue(json.loads(output)['error'])

    def test_artist_browse_is_explicit_and_bounded(self):
        artist = json.dumps({'id': CHANNEL, 'kind': 'artist', 'url': f'https://www.youtube.com/channel/{CHANNEL}'})
        with patch.object(d, 'DiscoveryYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'_type': 'playlist', 'entries': []}
            result = json.loads(d.browse(artist, 'all', 999, 'browse', callback()))
            self.assertEqual(result['error'], '')
            client.extract_info.assert_called_once_with(f'https://www.youtube.com/channel/{CHANNEL}/videos', download=False)
            self.assertEqual(engine.call_args.args[0]['playlist_items'], '1:60')

    def test_audio_resolution_is_ephemeral_and_filters_sensitive_headers(self):
        with patch.object(mobile, 'MobileYDL') as engine:
            client = engine.return_value.__enter__.return_value
            client.extract_info.return_value = {'url': STREAM, 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'aac',
                'duration': 222, 'http_headers': {'User-Agent': 'Blaze', 'Cookie': 'secret-cookie', 'Authorization': 'secret', 'Referer': 'bad\nheader'}}
            result = json.loads(d.resolve(item(), '', 'resolve-audio', callback()))
            self.assertEqual(result['stream']['url'], STREAM)
            self.assertEqual(result['stream']['mimeType'], 'audio/mp4')
            self.assertEqual(result['stream']['headers'], {'User-Agent': 'Blaze'})
            self.assertEqual(result['stream']['durationMs'], 222000)
            client.process_info.assert_not_called()
            self.assertTrue(engine.call_args.args[0]['noplaylist'])

    def test_video_resolution_pairs_video_with_audio_instead_of_silent_audio_only(self):
        with patch.object(mobile, 'MobileYDL') as engine:
            engine.return_value.__enter__.return_value.extract_info.return_value = {
                'duration': 30, 'requested_formats': [
                    {'url': STREAM, 'ext': 'mp4', 'vcodec': 'avc1', 'acodec': 'none'},
                    {'url': STREAM + '&audio=1', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'aac'}]}
            stream = json.loads(d.resolve(item('video'), '', 'resolve-video', callback()))['stream']
            self.assertEqual(stream['mimeType'], 'video/mp4')
            self.assertEqual(stream['audioMimeType'], 'audio/mp4')
            self.assertTrue(stream['audioUrl'].endswith('&audio=1'))
            expression = engine.call_args.args[0]['format']
            self.assertEqual(expression, d._VIDEO_FORMAT)
        # Exercise the pinned yt-dlp selector itself: a higher-ranked AV1 stream
        # must not displace AVC/AAC, and VP9 remains a usable explicit fallback.
        formats = [
            {'format_id': 'aac', 'url': STREAM, 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a.40.2'},
            {'format_id': 'opus', 'url': STREAM, 'ext': 'webm', 'vcodec': 'none', 'acodec': 'opus'},
            {'format_id': 'avc', 'url': STREAM, 'ext': 'mp4', 'height': 1080, 'vcodec': 'avc1.640028', 'acodec': 'none'},
            {'format_id': 'vp9', 'url': STREAM, 'ext': 'webm', 'height': 1080, 'vcodec': 'vp9', 'acodec': 'none'},
            {'format_id': 'av1', 'url': STREAM, 'ext': 'mp4', 'height': 1080, 'vcodec': 'av01.0.08M.08', 'acodec': 'none'},
        ]
        with d.YoutubeDL({'quiet': True, 'no_warnings': True}) as selector:
            choose = selector.build_format_selector(expression)
            context = {'formats': formats, 'has_merged_format': False, 'incomplete_formats': False}
            self.assertEqual(list(choose(context))[0]['format_id'], 'avc+aac')
            context['formats'] = [f for f in formats if f['format_id'] != 'avc']
            self.assertEqual(list(choose(context))[0]['format_id'], 'vp9+opus')
            context['formats'] = [f for f in formats if f['format_id'] in ('av1', 'aac', 'opus')]
            self.assertEqual(list(choose(context)), [])

    def test_selected_stream_rejects_non_provider_host_and_audio_only_video(self):
        for media in ({'url': 'https://127.0.0.1/private', 'vcodec': 'none', 'acodec': 'aac'},
                      {'url': STREAM, 'vcodec': 'none', 'acodec': 'aac'}):
            with self.subTest(media=media), patch.object(mobile, 'MobileYDL') as engine:
                engine.return_value.__enter__.return_value.extract_info.return_value = media
                output = json.loads(d.resolve(item('video'), '', 'invalid-stream', callback()))
                self.assertIn('error', output)
                self.assertNotIn('stream', output)

    def test_native_stream_cancellation_does_not_cancel_download_session(self):
        queue_session = mobile.Session(callback())
        mobile._sessions['existing-download'] = queue_session
        try:
            with patch.object(mobile, 'MobileYDL') as engine:
                def extraction(*_args, **_kwargs):
                    d.cancel('resolve-cancel')
                    return {'url': STREAM, 'vcodec': 'none', 'acodec': 'aac'}
                engine.return_value.__enter__.return_value.extract_info.side_effect = extraction
                result = json.loads(d.resolve(item(), '', 'resolve-cancel', callback()))
                self.assertTrue(result['error'])
                self.assertFalse(queue_session.cancelled.is_set())
                self.assertEqual(list(mobile._sessions), ['existing-download'])
        finally:
            mobile._sessions.pop('existing-download')


if __name__ == '__main__':
    unittest.main()
