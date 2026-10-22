"""Anonymous desktop catalogue and bounded, explicitly selected playback cache.

The packaged downloader is the provider boundary: listing never resolves or
fetches every recording. Only an explicit preparation downloads a playable copy.
The web renderer receives opaque local image identifiers and local media only.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

_VIDEO = re.compile(r'^[A-Za-z0-9_-]{11}$')
_CHANNEL = re.compile(r'^UC[A-Za-z0-9_-]{22}$')
_COLLECTION = re.compile(r'^[A-Za-z0-9_-]{6,128}$')
_IMAGES = {'i.ytimg.com', 'i9.ytimg.com', 'yt3.ggpht.com', 'lh3.googleusercontent.com', 'yt3.googleusercontent.com'}
_SOURCE_HOSTS = {'www.youtube.com', 'youtube.com', 'music.youtube.com', 'youtu.be'}
MAX_MEDIA = 512 * 1024 * 1024
MAX_CACHE = 1024 * 1024 * 1024

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

class Cancelled(Exception):
    pass


class ImageRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not _https(newurl, _IMAGES):
            raise ValueError('Image redirect unavailable.')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def canonical_item(value, playable=False):
    if not isinstance(value, dict):
        raise ValueError('Choose a catalogue item.')
    kind = value.get('kind')
    normalized = normalize({'id': value.get('id'), '_blaze_kind': kind,
                            'url': value.get('url'), 'title': value.get('title'),
                            'artist': value.get('creator'), 'thumbnail': value.get('thumbnail'),
                            'duration': (value.get('durationMs', -1) / 1000
                                         if type(value.get('durationMs')) in (int, float) else -1)},
                           'songs' if kind == 'song' else 'all')
    if not normalized or normalized['kind'] != kind or playable and kind not in ('song', 'video'):
        raise ValueError('Choose a supported catalogue item.')
    return normalized


class Discovery:
    def __init__(self, directory, tools, ffmpeg):
        self.directory = Path(directory) / 'discovery'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.cache_directory = self.directory / 'playback'
        self.cache_directory.mkdir(exist_ok=True)
        self.tools, self.ffmpeg = Path(tools), Path(ffmpeg)
        self.lock = threading.RLock()
        self.jobs, self.metadata, self.images = OrderedDict(), OrderedDict(), OrderedDict()
        self.pictures, self.issued = OrderedDict(), OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='BlazeCatalogue')
        self.player_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='BlazePrepare')
        self.closed, self.pinned, self.epoch, self.profile_epoch = False, None, 0, 0
        self.profile_path = self.directory / 'history.json'
        self.profile = []
        try:
            value = json.loads(self.profile_path.read_text(encoding='utf-8')) if self.profile_path.stat().st_size <= 65536 else []
            if isinstance(value, list):
                for row in value[:30]:
                    try:
                        item = canonical_item(row, True)
                        item['plays'] = min(1000, max(1, int(row.get('plays', 1))))
                        self.profile.append(item)
                    except (ValueError, TypeError):
                        pass
        except (OSError, ValueError, TypeError):
            pass
        for row in self.profile:
            self.issued[(row['kind'], row['id'])] = dict(row)
        # Interrupted preparations are never playable or retained on restart.
        for child in self.cache_directory.iterdir():
            if child.is_dir() and child.name.startswith('prepare-') and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
        self._prune()

    def _executable(self):
        result = self.tools / ('yt-dlp.exe' if sys.platform == 'win32' else 'yt-dlp')
        if not result.is_file():
            raise ValueError('The downloader is missing. Reinstall the complete Blaze app.')
        return result

    def _new(self, kind, work):
        with self.lock:
            if self.closed:
                raise ValueError('Blaze is closing.')
            active = sum(job['kind'] == kind and job['status'] == 'pending' for job in self.jobs.values())
            if active >= (3 if kind == 'metadata' else 2):
                raise ValueError('A request is already running. Cancel it and try again.')
            identity = secrets.token_urlsafe(18)
            job = {'id': identity, 'kind': kind, 'status': 'pending', 'items': [], 'error': '',
                   'progress': 'Finding recordings…' if kind == 'metadata' else 'Preparing playback on this device…',
                   'cancel': threading.Event(), 'process': None,
                   'deadline': time.monotonic() + (25 if kind == 'metadata' else 125)}
            self.jobs[identity] = job
            for key in list(self.jobs):
                if len(self.jobs) <= 24:
                    break
                if self.jobs[key]['status'] != 'pending':
                    del self.jobs[key]
            pool = self.pool if kind == 'metadata' else self.player_pool
            job['future'] = pool.submit(self._run, job, work)
            return {'requestId': identity}

    def _run(self, job, work):
        try:
            self._check(job)
            value = work(job)
            with self.lock:
                self._check(job)
                job.update(value, status='ready', error='')
        except Cancelled:
            with self.lock:
                job.update(status='cancelled', error='Request cancelled.')
        except Exception:
            with self.lock:
                job.update(status='failed', error=('Playback could not be prepared. Try another recording or check your connection.'
                                                  if job['kind'] == 'prepare' else
                                                  'Could not reach the media service. Check your connection and try again.'))

    def _check(self, job):
        if self.closed or job['cancel'].is_set():
            raise Cancelled()

    def _stop_process(self, process):
        if process is None or process.poll() is not None:
            return
        try:
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                import os
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except OSError:
                pass

    def _command(self, job, arguments, seconds=20, workspace=None, output_limit=1024 * 1024):
        """Never shell out, expose provider errors, or accumulate unlimited output."""
        command = [str(self._executable()), '--ignore-config', '--no-cache-dir', '--quiet', '--no-warnings',
                   '--no-progress', '--no-call-home', '--socket-timeout', '8', '--retries', '0',
                   '--extractor-retries', '0', '--no-playlist']
        node = self.tools / ('node.exe' if sys.platform == 'win32' else 'node')
        if node.is_file():
            command += ['--js-runtimes', 'node:' + str(node)]
        # A flat listing can legitimately include a bounded playlist.
        command += arguments
        kwargs = {'start_new_session': True} if sys.platform != 'win32' else {
            'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        with tempfile.TemporaryFile(dir=self.directory) as output:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.DEVNULL, **kwargs)
            with self.lock:
                job['process'] = process
            deadline = min(time.monotonic() + seconds, job['deadline'])
            try:
                while process.poll() is None:
                    self._check(job)
                    if time.monotonic() >= deadline or output.tell() > output_limit:
                        raise ValueError('Request took too long or returned too much data.')
                    if workspace:
                        total = sum(p.stat().st_size for p in workspace.iterdir() if p.is_file())
                        with self.lock:
                            job['progress'] = f'Preparing playback on this device… {total // (1024 * 1024)} MB'
                        if total > MAX_MEDIA:
                            raise ValueError('Recording exceeds playback cache limit.')
                    job['cancel'].wait(.05)
                self._check(job)
                if process.returncode or output.tell() > output_limit:
                    raise ValueError('Provider unavailable.')
                output.seek(0)
                return output.read(output_limit + 1)
            finally:
                self._stop_process(process)
                process.wait(timeout=5)
                with self.lock:
                    if job['process'] is process:
                        job['process'] = None

    def _query(self, job, target, scope, limit):
        raw = self._command(job, ['--flat-playlist', '--skip-download', '--dump-single-json',
                                  '--playlist-items', f'1:{limit}', '--yes-playlist', '--', target])
        info = json.loads(raw)
        entries = info.get('entries') or [] if info.get('_type') in ('playlist', 'multi_video') else [info]
        found = OrderedDict()
        for row in itertools.islice(entries, limit):
            self._check(job)
            item = normalize(row, scope)
            if item:
                key = (item['kind'] if item['kind'] not in ('song', 'video') else 'video', item['id'])
                found.setdefault(key, item)
        return list(found.values())

    def _public(self, item):
        value = dict(item)
        with self.lock:
            value['profileEpoch'] = self.profile_epoch
            self.issued[(item['kind'], item['id'])] = dict(item)
            self.issued.move_to_end((item['kind'], item['id']))
            while len(self.issued) > 1024:
                self.issued.popitem(last=False)
        image = _https(item.get('thumbnail'), _IMAGES)
        if image:
            key = secrets.token_urlsafe(18)
            # Reuse a recent opaque mapping without disclosing the remote URL.
            with self.lock:
                key = next((key for key, url in self.images.items() if url == image), key)
                self.images[key] = image
                self.images.move_to_end(key)
                while len(self.images) > 512:
                    removed, _url = self.images.popitem(last=False)
                    self.pictures.pop(removed, None)
            value['thumbnail'] = '/api/discovery-image?id=' + key
        else:
            value['thumbnail'] = ''
        return value

    def _issued(self, value, playable=False):
        item = canonical_item(value, playable)
        with self.lock:
            known = self.issued.get((item['kind'], item['id']))
            if not known:
                raise ValueError('Search for this recording again.')
            return dict(known)

    def request(self, body):
        if not isinstance(body, dict):
            raise ValueError('Choose a discovery action.')
        action = body.get('action')
        scope = body.get('filter', 'all')
        limit = body.get('limit', 24)
        if type(limit) is not int or not 1 <= limit <= 60 or scope not in ('all', 'songs', 'videos', 'artists', 'playlists'):
            raise ValueError('Choose a supported search filter and limit.')
        profile = []
        with self.lock:
            epoch = self.epoch
        if action == 'search':
            query = body.get('query')
            if not isinstance(query, str) or not 1 <= len(query.strip()) <= 256 or any(ord(c) < 32 for c in query):
                raise ValueError('Enter a search between 1 and 256 characters.')
            query = query.strip()
            if scope == 'songs':
                target = 'https://music.youtube.com/search?' + urlencode({'q': query}) + '#songs'
            elif scope == 'videos':
                target = f'ytsearch{limit}:{query}'
            else:
                parameters = {'search_query': query}
                if scope in ('artists', 'playlists'):
                    parameters['sp'] = 'EgIQAg==' if scope == 'artists' else 'EgIQAw=='
                target = 'https://www.youtube.com/results?' + urlencode(parameters)
            key = (action, scope, query, limit)
        elif action == 'browse':
            item = self._issued(body.get('item'))
            if item['kind'] not in ('artist', 'playlist', 'album'):
                raise ValueError('Choose an artist, album or playlist.')
            target = item['url'] + ('/videos' if item['kind'] == 'artist' else '')
            scope = 'videos'
            key = (action, item['kind'], item['id'], limit)
        elif action == 'recommend':
            lane = body.get('lane', 'music')
            if lane not in ('music', 'videos'):
                raise ValueError('Choose music or video recommendations.')
            limit = min(limit, 18)
            with self.lock:
                profile = [dict(row) for row in self.profile]
            key = (action, lane, json.dumps(profile, sort_keys=True), limit)
        else:
            raise ValueError('Choose a discovery action.')

        def work(job):
            with self.lock:
                cached = self.metadata.get(key)
                if cached and cached[0] > time.monotonic():
                    self.metadata.move_to_end(key)
                    return {'items': [self._public(row) for row in cached[1]]}
            if action == 'recommend':
                queries, heard = _recommendation_plan(profile, lane)
                buckets = []
                for query in queries:
                    self._check(job)
                    try:
                        buckets.append(self._query(job, f'ytsearch12:{query}' if lane == 'videos' else
                                                   'https://music.youtube.com/search?' + urlencode({'q': query}) + '#songs',
                                                   'videos' if lane == 'videos' else 'songs', 12))
                    except Cancelled:
                        raise
                    except Exception:
                        continue
                items, seen, titles, creators = [], set(), set(), {}
                for candidates in itertools.zip_longest(*buckets):
                    for item in candidates:
                        if not item or item['kind'] not in ('song', 'video'):
                            continue
                        creator = item['creator'].casefold()
                        title = re.sub(r'[^\w]+', ' ', item['title'].casefold()).strip()
                        duration = item['durationMs']
                        if (item['id'] in seen or item['id'] in heard or title in titles or
                                creator and creators.get(creator, 0) >= 2 or duration >= 0 and not 30000 <= duration <= 1800000):
                            continue
                        items.append(item); seen.add(item['id']); titles.add(title)
                        creators[creator] = creators.get(creator, 0) + 1
                        if len(items) >= limit:
                            break
                    if len(items) >= limit:
                        break
                if not buckets:
                    raise ValueError('Provider unavailable.')
            else:
                items = self._query(job, target, scope, limit)
            self._check(job)
            if items:
                with self.lock:
                    if epoch == self.epoch:
                        self.metadata[key] = (time.monotonic() + (21600 if action == 'recommend' else 120), items)
                        self.metadata.move_to_end(key)
                        while len(self.metadata) > 12:
                            self.metadata.popitem(last=False)
            return {'items': [self._public(row) for row in items]}
        return self._new('metadata', work)

    def status(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job:
                raise ValueError('This request expired. Try again.')
            value = {key: job[key] for key in ('status', 'items', 'error', 'progress')}
            if 'item' in job:
                value['item'] = self._public(job['item'])
            return value

    def cancel(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job:
                return
            job['cancel'].set()
            job.update(status='cancelled', error='Request cancelled.')
            process = job['process']
            job['future'].cancel()
        self._stop_process(process)

    def _prune(self):
        files = sorted((p for p in self.cache_directory.iterdir() if p.is_file() and not p.is_symlink()),
                       key=lambda path: path.stat().st_mtime, reverse=True)
        pinned = self.pinned if self.pinned in files else None
        total, count = (pinned.stat().st_size, 1) if pinned else (0, 0)
        for path in files:
            if path == pinned:
                continue
            size = path.stat().st_size
            if total + size > MAX_CACHE or count >= 6:
                path.unlink(missing_ok=True)
            else:
                total += size
                count += 1

    def prepare(self, body):
        item = self._issued(body.get('item'), True)
        mode = body.get('mode', 'video' if item['kind'] == 'video' else 'audio')
        if mode not in ('audio', 'video'):
            raise ValueError('Choose audio or video playback.')
        if item['durationMs'] > 7200000:
            raise ValueError('Choose a recording shorter than two hours for playback.')
        suffix = '.mp4' if mode == 'video' else '.m4a'
        destination = self.cache_directory / (item['id'] + '-' + mode + suffix)

        def work(job):
            if destination.is_file() and 0 < destination.stat().st_size <= MAX_MEDIA:
                with self.lock:
                    destination.touch()
                    self._prune()
                return {'path': destination, 'item': item, 'progress': 'Ready to play.'}
            workspace = Path(tempfile.mkdtemp(prefix='prepare-', dir=self.cache_directory))
            try:
                # AVC/AAC is shared by WebView2, WKWebView and supported GTK media
                # backends. Do not promise that arbitrary codecs can play in HTML.
                formats = ('bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/'
                           'best[height<=720][vcodec^=avc1][acodec^=mp4a]' if mode == 'video'
                           else 'bestaudio[ext=m4a]/best[ext=mp4][acodec^=mp4a]')
                arguments = ['--format', formats, '--max-filesize', str(MAX_MEDIA), '--ffmpeg-location', str(self.ffmpeg),
                             '--output', str(workspace / ('selected.%(ext)s')), '--no-part',
                             '--no-write-info-json', '--no-write-thumbnail', '--no-write-subs', '--no-write-auto-subs']
                if mode == 'video':
                    arguments += ['--merge-output-format', 'mp4', '--remux-video', 'mp4']
                else:
                    arguments += ['--extract-audio', '--audio-format', 'm4a']
                arguments += ['--', item['url']]
                self._command(job, arguments, seconds=120, workspace=workspace, output_limit=65536)
                self._check(job)
                source = workspace / ('selected' + suffix)
                if not source.is_file() or not 0 < source.stat().st_size <= MAX_MEDIA:
                    raise ValueError('No playable recording.')
                with self.lock:
                    source.replace(destination)
                    self._prune()
                return {'path': destination, 'item': item, 'progress': 'Ready to play.'}
            finally:
                shutil.rmtree(workspace, ignore_errors=True)
        return self._new('prepare', work)

    def select(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job or job['kind'] != 'prepare' or job['status'] != 'ready':
                raise ValueError('Wait until playback is ready.')
            path = job['path']
            if not path.is_file() or not path.resolve().is_relative_to(self.cache_directory.resolve()):
                raise ValueError('The playback copy expired. Select the recording again.')
            self.pinned = path
            return path, self._public(job['item'])

    def history(self):
        with self.lock:
            return [self._public(row) for row in self.profile]

    def listened(self, body):
        item = self._issued(body.get('item'), True)
        seconds = body.get('seconds')
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 10 <= seconds <= 7200:
            raise ValueError('Only active listening is counted.')
        with self.lock:
            if body['item'].get('profileEpoch') != self.profile_epoch:
                raise ValueError('Listening history was reset. Select the recording again.')
            previous = next((row for row in self.profile if row['id'] == item['id']), None)
            item['plays'] = min(1000, (previous.get('plays', 0) if previous else 0) + 1)
            self.profile = [item] + [row for row in self.profile if row['id'] != item['id']][:29]
            temporary = self.profile_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.profile), encoding='utf-8')
            temporary.replace(self.profile_path)
            self.epoch += 1
            self.metadata.clear()

    def reset(self):
        with self.lock:
            self.profile = []
            self.epoch += 1
            self.profile_epoch += 1
            self.metadata.clear()
            self.profile_path.unlink(missing_ok=True)

    def image(self, identity):
        with self.lock:
            if identity in self.pictures:
                self.pictures.move_to_end(identity)
                return self.pictures[identity]
            url = self.images.get(identity)
        if not url:
            raise ValueError('Image expired.')
        request = Request(url, headers={'User-Agent': 'Blaze/1.0', 'Accept': 'image/jpeg,image/png,image/webp'})
        with build_opener(ImageRedirects()).open(request, timeout=8) as response:
            kind = response.headers.get_content_type()
            if kind not in ('image/jpeg', 'image/png', 'image/webp'):
                raise ValueError('Unsupported image.')
            data = response.read(1024 * 1024 + 1)
        if not data or len(data) > 1024 * 1024:
            raise ValueError('Image too large.')
        with self.lock:
            self.pictures[identity] = (data, kind)
            self.pictures.move_to_end(identity)
            while len(self.pictures) > 32:
                self.pictures.popitem(last=False)
        return data, kind

    def close(self):
        with self.lock:
            self.closed = True
            identities = list(self.jobs)
        for identity in identities:
            self.cancel(identity)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.player_pool.shutdown(wait=False, cancel_futures=True)
