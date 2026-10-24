"""Deterministic catalogue used only by explicit native and browser QA runs.

The application never installs this fixture in a normal launch. Its images and
media stay in the automated test's isolated data directory, outside the bundle.
"""
import threading
import time
import uuid
from pathlib import Path


class MacSmokeCatalogue:
    def __init__(self, directory, initial_media, video=None):
        self.directory = Path(directory)
        self.artwork = self.directory / 'discovery-fixtures'
        self.audio = Path(initial_media)
        self.video = Path(video) if video else self.directory / 'downloads/blaze-video-fixture.mp4'
        self.lock = threading.RLock()
        self.jobs = {}
        self.heard = []
        self.closed = False
        self.requests = []
        self.home = [
            self.item('aaaaaaaaaaa', 'An evening at the keys', 'Juniper', image='piano'),
            self.item('bbbbbbbbbbb', 'Acoustic sessions', 'Mira Lane', image='acoustic'),
            self.item('ccccccccccc', 'After hours', 'North Quartet', image='jazz'),
            self.item('ddddddddddd', 'Golden Hour', 'The Northlights', image='sunset'),
            self.item('eeeeeeeeeee', 'Quiet Roads', 'Mira Lane', image='acoustic'),
            self.item('fffffffffff', 'Live by the water', 'Juniper', kind='video', image='sunset'),
        ]

    @staticmethod
    def item(identity, title, creator, kind='song', image='sunset'):
        return {'id': identity, 'kind': kind, 'title': title, 'creator': creator,
                'url': 'https://www.youtube.com/watch?v=' + identity,
                'thumbnail': '/api/discovery-image?id=' + image,
                'durationMs': 12000, 'localJobId': '', 'profileEpoch': 0}

    def _job(self, **value):
        with self.lock:
            if self.closed:
                raise ValueError('The test catalogue is closed.')
            identity = uuid.uuid4().hex
            self.jobs[identity] = dict(ready=time.monotonic() + .04, cancelled=False, **value)
            return {'requestId': identity}

    def request(self, body):
        action = body.get('action')
        query = str(body.get('query', '')).strip()
        self.requests.append(dict(body))
        rows = self.home
        if action == 'search':
            if body.get('filter') == 'videos':
                rows = [self.item('fffffffffff', query + ' live session', 'Juniper', kind='video')]
            else:
                rows = [self.item('aaaaaaaaaaa', query + ' acoustic session', 'Mira Lane', image='acoustic'),
                        self.item('fffffffffff', query + ' live session', 'Juniper', kind='video')]
        elif action == 'browse':
            rows = self.home[:3]
        return self._job(items=rows, error=None)

    def status(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if job is None:
                raise ValueError('The test request expired.')
            late = dict(job['item']) if job.get('late_response') else None
        if late:
            # A controlled in-flight provider reply may complete after the
            # caller cancels it. The client must reject that stale generation.
            time.sleep(1.2)
            return {'status': 'ready', 'item': late, 'error': None}
        with self.lock:
            if job['cancelled']:
                return {'status': 'cancelled', 'error': 'Request cancelled.'}
            if time.monotonic() < job['ready']:
                return {'status': 'pending', 'progress': 'Preparing local fixture…'}
            if 'item' in job:
                return {'status': 'ready', 'item': job['item'], 'error': None}
            return {'status': 'ready', 'items': job['items'], 'error': None}

    def cancel(self, identity):
        with self.lock:
            if identity in self.jobs:
                self.jobs[identity]['cancelled'] = True

    def prepare(self, body):
        item = body.get('item')
        if not isinstance(item, dict) or item.get('id') not in {row['id'] for row in self.home}:
            raise ValueError('Choose an issued test recording.')
        return self._job(item=dict(item), late_response=item['title'].startswith('slow handoff'))

    def select(self, identity):
        with self.lock:
            if self.status(identity)['status'] != 'ready' or 'item' not in self.jobs[identity]:
                raise ValueError('Wait for the prepared test recording.')
            item = self.jobs[identity]['item']
            path = self.video if item['kind'] == 'video' else self.audio
            if not path.is_file():
                raise ValueError('The local media fixture is missing.')
            return path, dict(item)

    def image(self, identity):
        if identity not in ('piano', 'acoustic', 'jazz', 'sunset'):
            raise ValueError('Unknown test image.')
        return (self.artwork / (identity + '.png')).read_bytes(), 'image/png'

    def history(self):
        return self.heard

    def listened(self, body):
        self.heard = [dict(body['item'])]

    def reset(self):
        self.heard = []

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                job['cancelled'] = True
