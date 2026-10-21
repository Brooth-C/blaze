"""Bounded anonymous catalogue metadata and explicitly selected stream resolution.

The search path never downloads media, starts FFmpeg or resolves every result.
Stream URLs are ephemeral; only canonical identities leave the catalogue path.
"""
import contextvars
from contextlib import contextmanager
import itertools
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, quote, urlencode, urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube._search import YoutubeMusicSearchURLIE


_VIDEO = re.compile(r'^[A-Za-z0-9_-]{11}$')
_CHANNEL = re.compile(r'^UC[A-Za-z0-9_-]{22}$')
_COLLECTION = re.compile(r'^[A-Za-z0-9_-]{6,128}$')
_IMAGES = {'i.ytimg.com', 'i9.ytimg.com', 'yt3.ggpht.com', 'lh3.googleusercontent.com', 'yt3.googleusercontent.com'}
_SOURCE_HOSTS = {'www.youtube.com', 'youtube.com', 'music.youtube.com', 'youtu.be'}
# Keep remote video compatible with Android's built-in decoders. Prefer AVC/AAC,
# then VP9 with available audio; never silently select an AV1-only rendition.
_VIDEO_FORMAT = ('bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/'
                 'best[height<=1080][vcodec^=avc1][acodec^=mp4a]/'
                 'bestvideo[height<=1080][vcodec^=vp9]+bestaudio/'
                 'best[height<=1080][vcodec^=vp9]')
_sessions = {}
_lock = threading.Lock()
_operation = contextvars.ContextVar('blaze_discovery_operation', default=None)


class DiscoveryCancelled(Exception):
    pass


class Operation:
    def __init__(self, callback, seconds=20):
        self.callback = callback
        self.cancelled = threading.Event()
        self.deadline = time.monotonic() + seconds
        self.native_cancel = None

    def isCancelled(self):
        return self.cancelled.is_set() or self.callback.isCancelled() or time.monotonic() >= self.deadline

    def check(self):
        if self.isCancelled():
            raise DiscoveryCancelled('Request cancelled or timed out.')


@contextmanager
def _session(token, callback):
    operation = Operation(callback)
    with _lock:
        if token in _sessions:
            raise ValueError('Duplicate discovery request')
        _sessions[token] = operation
    context = _operation.set(operation)
    timer = threading.Timer(20, lambda: cancel(token))
    timer.daemon = True
    timer.start()
    try:
        operation.check()
        yield operation
    finally:
        timer.cancel()
        _operation.reset(context)
        with _lock:
            _sessions.pop(token, None)


def cancel(token):
    with _lock:
        operation = _sessions.get(token)
    if operation:
        operation.cancelled.set()
        native_cancel = operation.native_cancel
        if native_cancel:
            native_cancel()


class QuietLogger:
    def debug(self, _message):
        operation = _operation.get()
        if operation:
            operation.check()
    warning = debug
    error = debug


class DiscoveryYDL(YoutubeDL):
    def urlopen(self, request):
        operation = _operation.get()
        if operation:
            operation.check()
        response = super().urlopen(request)
        if operation:
            try:
                operation.check()
            except DiscoveryCancelled:
                response.close()
                raise
        return response


def _at(value, *path):
    for key in path:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError):
            return None
    return value


def _runs(value):
    runs = value.get('runs', []) if isinstance(value, dict) else []
    return [run for run in runs if isinstance(run, dict)]


class BlazeMusicSearch(YoutubeMusicSearchURLIE):
    """Keep row metadata discarded by the pinned upstream flat music adapter.

    The yt-dlp adapter still owns transport, section filters and continuations.
    This narrow renderer seam is covered by source-shaped offline fixtures.
    """
    IE_NAME = 'blaze:music:search'

    def _music_reponsive_list_entry(self, renderer):
        result = super()._music_reponsive_list_entry(renderer)
        if not isinstance(result, dict):
            return result
        columns = renderer.get('flexColumns') or []
        title_node = _at(columns, 0, 'musicResponsiveListItemFlexColumnRenderer', 'text')
        title = ''.join(str(run.get('text') or '') for run in _runs(title_node))
        if title:
            result['title'] = title
        details = _runs(_at(columns, 1, 'musicResponsiveListItemFlexColumnRenderer', 'text'))
        named_artists = [str(run.get('text') or '') for run in details
                         if str(_at(run, 'navigationEndpoint', 'browseEndpoint', 'browseId') or '').startswith('UC')]
        if named_artists:
            result['artist'] = ' & '.join(named_artists)
        else:
            for run in details:
                text = str(run.get('text') or '').strip()
                if text and text not in ('Song', 'Video', 'Album', 'Artist', 'Playlist', '•', '&', ',') and not re.fullmatch(r'\d+(?::\d{2}){1,2}', text):
                    result['artist'] = text
                    break
        thumbnail = _at(renderer, 'thumbnail', 'musicThumbnailRenderer', 'thumbnail', 'thumbnails')
        if isinstance(thumbnail, list):
            result['thumbnails'] = thumbnail
        fixed = _at(renderer, 'fixedColumns', 0, 'musicResponsiveListItemFixedColumnRenderer', 'text')
        duration_text = ''.join(str(run.get('text') or '') for run in _runs(fixed)).strip()
        if not re.fullmatch(r'\d+(?::\d{2}){1,2}', duration_text):
            duration_text = next((str(run.get('text') or '').strip() for run in reversed(details)
                                  if re.fullmatch(r'\d+(?::\d{2}){1,2}', str(run.get('text') or '').strip())), '')
        if duration_text:
            seconds = 0
            for part in duration_text.split(':'):
                seconds = seconds * 60 + int(part)
            result['duration'] = seconds
        identity = str(result.get('id') or '')
        if _VIDEO.fullmatch(identity):
            result['_blaze_kind'] = 'video' if any(str(run.get('text') or '').strip() == 'Video' for run in details) else 'song'
        return result


def _text(value, limit):
    if not isinstance(value, str):
        return ''
    return ''.join(' ' if ord(char) < 32 or ord(char) == 127 else char for char in value).strip()[:limit]


def _https(value, hosts=None, stream=False):
    if not isinstance(value, str) or len(value) > (16384 if stream else 8192) or any(ord(c) < 32 for c in value):
        return ''
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password or parsed.port is not None:
            return ''
        if hosts is not None and host not in hosts:
            return ''
        if stream and not (host == 'googlevideo.com' or host.endswith('.googlevideo.com')):
            return ''
        return value
    except ValueError:
        return ''


def _duration(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 604800:
        return round(value * 1000)
    return -1


def _thumbnail(entry, identity='', video=False):
    candidates = entry.get('thumbnails') or []
    if isinstance(candidates, list):
        for candidate in sorted((c for c in candidates if isinstance(c, dict)),
                                key=lambda c: abs((c.get('width') or 320) - 320) if isinstance(c.get('width'), (int, float)) else 0):
            url = _https(candidate.get('url'), _IMAGES)
            if url:
                return url
    image = _https(entry.get('thumbnail'), _IMAGES)
    if image:
        return image
    return f'https://i.ytimg.com/vi/{identity}/mqdefault.jpg' if video else ''


def normalize(entry, scope='all'):
    """Normalize flat provider entries without performing further extraction."""
    if not isinstance(entry, dict):
        return None
    candidate = _https(entry.get('webpage_url') or entry.get('url'), _SOURCE_HOSTS)
    identity = str(entry.get('id') or '')
    parsed = urlsplit(candidate) if candidate else None
    if parsed and parsed.hostname == 'youtu.be':
        identity = parsed.path.strip('/')
    elif parsed and parsed.path == '/watch':
        identity = (parse_qs(parsed.query).get('v') or [identity])[0]
    kind = entry.get('_blaze_kind')
    if parsed and parsed.path == '/playlist':
        identity = (parse_qs(parsed.query).get('list') or [''])[0]
        if not _COLLECTION.fullmatch(identity):
            return None
        kind = 'playlist'; candidate = 'https://www.youtube.com/playlist?' + urlencode({'list': identity})
    elif _VIDEO.fullmatch(identity):
        kind = 'song' if scope == 'songs' or kind == 'song' else 'video'
        candidate = f'https://www.youtube.com/watch?v={identity}'
    elif _CHANNEL.fullmatch(identity):
        kind = 'artist'
        candidate = f'https://www.youtube.com/channel/{identity}'
    elif parsed and '/channel/' in parsed.path:
        identity = parsed.path.rstrip('/').rsplit('/', 1)[-1]
        if not _CHANNEL.fullmatch(identity):
            return None
        kind = 'artist'; candidate = f'https://www.youtube.com/channel/{identity}'
    elif parsed and parsed.path.startswith('/browse/'):
        identity = parsed.path.rstrip('/').rsplit('/', 1)[-1]
        if _CHANNEL.fullmatch(identity):
            kind = 'artist'; candidate = f'https://www.youtube.com/channel/{identity}'
        elif identity.startswith('VL') and _COLLECTION.fullmatch(identity[2:]):
            identity = identity[2:]; kind = 'playlist'
            candidate = 'https://www.youtube.com/playlist?' + urlencode({'list': identity})
        elif identity.startswith('MPRE') and _COLLECTION.fullmatch(identity):
            kind = 'album'; candidate = f'https://music.youtube.com/browse/{identity}'
        else:
            return None
    else:
        return None
    if not candidate or kind not in ('song', 'video', 'artist', 'playlist', 'album'):
        return None
    title = _text(entry.get('title') or entry.get('channel') or entry.get('uploader'), 300)
    if not title:
        return None
    creator = _text(entry.get('artist') or entry.get('channel') or entry.get('uploader') or entry.get('creator'), 200)
    return {'id': identity, 'kind': kind, 'title': title, 'creator': creator,
            'url': candidate, 'thumbnail': _thumbnail(entry, identity, kind in ('song', 'video')),
            'durationMs': _duration(entry.get('duration')), 'localJobId': ''}


def _options(limit):
    return {'extract_flat': 'in_playlist', 'skip_download': True, 'ignoreconfig': True,
            'cachedir': False, 'quiet': True, 'no_warnings': True, 'noprogress': True,
            'logger': QuietLogger(), 'socket_timeout': 8, 'retries': 0, 'extractor_retries': 0,
            'playlist_items': f'1:{limit}', 'postprocessors': [], 'fixup': 'never',
            'writethumbnail': False, 'writeinfojson': False, 'writesubtitles': False}


def _entries(info, limit):
    if not isinstance(info, dict):
        return []
    if info.get('_type') not in ('playlist', 'multi_video'):
        return [info]
    return itertools.islice(info.get('entries') or (), limit)


def _list(target, scope, limit, operation):
    found = {}
    with DiscoveryYDL(_options(limit), auto_init=False) as engine:
        # Register this narrow metadata-preserving adapter first, then all normal
        # extractors. Both remain tied to the app's existing pinned yt-dlp package.
        engine.add_info_extractor(BlazeMusicSearch())
        engine.add_default_info_extractors()
        info = engine.extract_info(target, download=False)
        for entry in _entries(info, limit):
            operation.check()
            item = normalize(entry, scope)
            if item:
                key = (item['kind'] if item['kind'] in ('artist', 'playlist', 'album') else 'video', item['id'])
                found.setdefault(key, item)
            if len(found) >= limit:
                break
    return list(found.values())


def _failure(error):
    # Provider exceptions may contain signed URLs/headers; never return their raw text.
    text = str(error).lower()
    if isinstance(error, DiscoveryCancelled):
        return 'This request was cancelled or took too long. Try again.'
    if '429' in text or 'too many requests' in text:
        return 'The service is busy. Wait a moment and try again.'
    if 'sign in' in text or 'login' in text or 'private video' in text:
        return 'This recording needs an account or is not publicly available.'
    if 'not available' in text or 'unavailable' in text or 'removed' in text:
        return 'This recording is unavailable. Try another result.'
    return 'Could not reach the media service. Check your connection and try again.'


def _result(value):
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode('utf-8')) > 262144:
        return json.dumps({'items': [], 'error': 'The response was too large. Refine your search.'})
    return encoded


def _recommendation_plan(history, lane):
    """Rank local listening signals; send only small search terms to YouTube."""
    artists, heard, titles = {}, set(), []
    for index, row in enumerate(history[:30]):
        if not isinstance(row, dict) or not _VIDEO.fullmatch(str(row.get('id') or '')):
            continue
        heard.add(row['id'])
        creator, title = _text(row.get('creator'), 120), _text(row.get('title'), 120)
        plays = row.get('plays', 0)
        plays = min(20, max(0, plays)) if type(plays) is int else 0
        weight = 1 / (index + 1) + plays * .15 + (1.5 if row.get('favorite') is True else 0)
        if creator:
            key = creator.casefold()
            previous = artists.get(key, (creator, 0))
            artists[key] = (creator, previous[1] + weight)
        elif title:
            titles.append(title)
    ranked = sorted(artists.values(), key=lambda artist: artist[1], reverse=True)
    suffix = ' official music video' if lane == 'videos' else ' songs'
    queries = [name + suffix for name, _weight in ranked[:2]]
    if not queries and titles:
        queries.append(titles[0] + ' music')
    # Anonymous discovery, not a claim to reproduce a signed-in YouTube feed or chart.
    year = time.gmtime().tm_year
    general = [f'popular music {year}', f'new songs {year}', 'popular international songs']
    queries.append(general[int(time.time() // 86400) % len(general)] + (' official music video' if lane == 'videos' else ''))
    if len(queries) == 1:
        queries.append(general[(int(time.time() // 86400) + 1) % len(general)])
    return queries[:3], heard


def recommend(profile_json, lane, limit, token, callback):
    """Anonymous bounded candidate retrieval, local seeds, diversity and recent exclusions."""
    try:
        if not isinstance(profile_json, str) or len(profile_json) > 32768 or lane not in ('music', 'videos'):
            raise ValueError('Invalid recommendation profile')
        history = json.loads(profile_json)
        if not isinstance(history, list):
            raise ValueError('Invalid recommendation history')
        limit = max(1, min(int(limit), 18))
        queries, heard = _recommendation_plan(history, lane)
        scope = 'videos' if lane == 'videos' else 'songs'
        buckets, failure = [], None
        with _session(token, callback) as operation:
            for query in queries:
                try:
                    operation.check()
                    target = (f'ytsearch12:{query}' if scope == 'videos' else
                              'https://music.youtube.com/search?q=' + quote(query) + '#songs')
                    buckets.append(_list(target, scope, 12, operation))
                except DiscoveryCancelled as error:
                    failure = error
                    break
                except Exception as error:
                    failure = error
            picked, identities, names, creators = [], set(), set(), {}
            # Round-robin seed and general results, rather than filling every slot
            # with a single artist. At most two recordings from the same creator.
            for candidates in itertools.zip_longest(*buckets):
                for candidate in candidates:
                    if not isinstance(candidate, dict) or candidate.get('kind') not in ('song', 'video'):
                        continue
                    identity = candidate.get('id')
                    if identity in heard or identity in identities or not _VIDEO.fullmatch(str(identity or '')):
                        continue
                    duration = candidate.get('durationMs', -1)
                    if duration >= 0 and not 30000 <= duration <= 1800000:
                        continue
                    creator = _text(candidate.get('creator'), 200).casefold()
                    title = re.sub(r'[^\w]+', ' ', _text(candidate.get('title'), 300).casefold()).strip()
                    name = title
                    if name in names or (creator and creators.get(creator, 0) >= 2):
                        continue
                    identities.add(identity); names.add(name)
                    creators[creator] = creators.get(creator, 0) + 1
                    picked.append(candidate)
                    if len(picked) == limit:
                        return _result({'items': picked, 'error': ''})
            return _result({'items': picked, 'error': _failure(failure) if not picked and failure else ''})
    except Exception as error:
        return _result({'items': [], 'error': _failure(error)})


def search(query, filter_name, limit, token, callback):
    try:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 256 or any(ord(c) < 32 for c in query):
            raise ValueError('Invalid query')
        if filter_name not in ('all', 'songs', 'videos', 'artists', 'playlists'):
            raise ValueError('Invalid scope')
        limit = max(1, min(int(limit), 60))
        query = query.strip()
        if filter_name == 'videos':
            target = f'ytsearch{limit}:{query}'
        elif filter_name == 'artists':
            target = 'https://www.youtube.com/results?' + urlencode({'search_query': query, 'sp': 'EgIQAg=='})
        elif filter_name == 'playlists':
            target = 'https://www.youtube.com/results?' + urlencode({'search_query': query, 'sp': 'EgIQAw=='})
        else:
            target = 'https://music.youtube.com/search?q=' + quote(query) + ('#songs' if filter_name == 'songs' else '')
        with _session(token, callback) as operation:
            items = _list(target, filter_name, limit, operation)
            operation.check()
            return _result({'items': items, 'error': ''})
    except Exception as error:
        return _result({'items': [], 'error': _failure(error)})


def browse(item_json, _filter_name, limit, token, callback):
    try:
        item = json.loads(item_json)
        target = _https(item.get('url'), _SOURCE_HOSTS)
        if not target or item.get('kind') not in ('artist', 'playlist', 'album'):
            raise ValueError('Invalid collection')
        if item['kind'] == 'artist':
            if not _CHANNEL.fullmatch(str(item.get('id') or '')):
                raise ValueError('Invalid artist')
            target = f'https://www.youtube.com/channel/{item["id"]}/videos'
        elif item['kind'] == 'playlist':
            identity = str(item.get('id') or '')
            if not _COLLECTION.fullmatch(identity):
                raise ValueError('Invalid playlist')
            target = 'https://www.youtube.com/playlist?' + urlencode({'list': identity})
        else:
            identity = str(item.get('id') or '')
            if not identity.startswith('MPRE') or not _COLLECTION.fullmatch(identity):
                raise ValueError('Invalid album')
            target = f'https://music.youtube.com/browse/{identity}'
        with _session(token, callback) as operation:
            items = _list(target, 'videos', max(1, min(int(limit), 60)), operation)
            operation.check()
            return _result({'items': items, 'error': ''})
    except Exception as error:
        return _result({'items': [], 'error': _failure(error)})


def _mime(info):
    extension = info.get('ext') or ''
    video = info.get('vcodec') not in (None, 'none')
    if extension in ('mp4', 'm4a'):
        return 'video/mp4' if video else 'audio/mp4'
    if extension == 'webm':
        return 'video/webm' if video else 'audio/webm'
    if extension in ('mp3', 'opus', 'ogg'):
        return {'mp3': 'audio/mpeg', 'opus': 'audio/ogg', 'ogg': 'audio/ogg'}[extension]
    return ''


def resolve(item_json, quickjs_path, token, callback):
    try:
        item = json.loads(item_json)
        identity = str(item.get('id') or '')
        if not _VIDEO.fullmatch(identity) or item.get('kind') not in ('song', 'video'):
            raise ValueError('Choose a recording')
        with _session(token, callback) as operation:
            # Reuse the downloader's established per-token native process cancellation,
            # but never invoke download() or process_info(). The independent token and
            # context prevent a playback cancellation from touching the queue worker.
            import blaze_mobile as mobile
            native_token = 'discovery:' + token
            native = mobile.Session(operation)
            with mobile._lock:
                mobile._sessions[native_token] = native
            operation.native_cancel = lambda: mobile.cancel(native_token)
            native_context = mobile._session.set(native)
            try:
                options = _options(1)
                options.update({'extract_flat': False, 'noplaylist': True,
                                'format': _VIDEO_FORMAT if item['kind'] == 'video' else 'bestaudio/best'})
                if quickjs_path and Path(quickjs_path).is_file():
                    options['js_runtimes'] = {'quickjs': {'path': quickjs_path}}
                with mobile.MobileYDL(options) as engine:
                    info = engine.extract_info(f'https://www.youtube.com/watch?v={identity}', download=False)
                    operation.check()
                if not isinstance(info, dict) or info.get('is_live') or info.get('live_status') == 'is_upcoming':
                    raise ValueError('This recording cannot be played')
                formats = info.get('requested_formats') or []
                video = next((f for f in formats if f.get('vcodec') not in (None, 'none')), None)
                audio = next((f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')), None)
                primary = video if item['kind'] == 'video' and video else info
                url = _https(primary.get('url'), stream=True)
                if not url or item['kind'] == 'video' and (primary.get('vcodec') in (None, 'none') or primary.get('acodec') == 'none' and audio is None):
                    raise ValueError('No playable stream')
                audio_url = _https(audio.get('url'), stream=True) if audio else ''
                if audio and not audio_url:
                    raise ValueError('No playable audio')
                headers = {}
                for source in (info.get('http_headers') or {}, primary.get('http_headers') or {}):
                    for key in ('User-Agent', 'Referer', 'Origin', 'Accept', 'Accept-Language'):
                        value = source.get(key)
                        if isinstance(value, str) and len(value) <= 2048 and not any(ord(c) < 32 for c in value):
                            headers[key] = value
                return _result({'stream': {'url': url, 'mimeType': _mime(primary), 'headers': headers,
                                          'durationMs': _duration(info.get('duration')),
                                          'audioUrl': audio_url, 'audioMimeType': _mime(audio) if audio else ''}, 'error': ''})
            finally:
                operation.native_cancel = None
                mobile._session.reset(native_context)
                with mobile._lock:
                    mobile._sessions.pop(native_token, None)
    except Exception as error:
        return _result({'error': _failure(error)})
