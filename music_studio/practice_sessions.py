"""Local practice settings, retained imports, and recording-bound chord guides."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

MAX_BYTES = 2 * 1024 ** 3
MAX_SECONDS = 7200
MODES = ('original', 'piano', 'backing')
IDENTIFIER = re.compile(r'[0-9a-f]{32}')
ANALYSIS_ID = re.compile(r'[0-9a-f]{64}')


def fingerprint(source):
    path = Path(source).resolve(strict=True)
    stat = path.stat()
    if not path.is_file() or not 0 < stat.st_size <= MAX_BYTES:
        raise ValueError('Choose a readable recording smaller than 2 GB.')
    return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def recording_id(identity):
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


def identity_value(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 5 or
            not isinstance(value[0], str) or not Path(value[0]).is_absolute() or
            len(value[0]) > 4096 or any(type(n) is not int or n < 0 for n in value[1:]) or
            not 0 < value[3] <= MAX_BYTES):
        raise ValueError('Saved recording identity is invalid.')
    return tuple(value)


def settings_value(body):
    if not isinstance(body, dict):
        raise ValueError('Saved practice settings are invalid.')
    def number(name, default, lower, upper, nullable=False):
        value = body.get(name, default)
        if value is None and nullable:
            return None
        if (type(value) not in (int, float) or not math.isfinite(value) or
                not lower <= value <= upper):
            raise ValueError('Choose a valid practice ' + name + '.')
        return float(value)
    transpose = body.get('transpose', 0)
    if type(transpose) is not int or not -12 <= transpose <= 12:
        raise ValueError('Choose a transpose between −12 and +12 semitones.')
    value = {'transpose': transpose, 'position': number('position', 0, 0, MAX_SECONDS),
             'rate': number('rate', 1, .5, 1.5),
             'loopStart': number('loopStart', None, 0, MAX_SECONDS, True),
             'loopEnd': number('loopEnd', None, 0, MAX_SECONDS, True),
             'loopEnabled': body.get('loopEnabled', False), 'mode': body.get('mode', 'original')}
    if type(value['loopEnabled']) is not bool or value['mode'] not in MODES:
        raise ValueError('Choose a valid practice listening mode and loop.')
    start, end = value['loopStart'], value['loopEnd']
    if ((start is not None and end is not None and end <= start) or
            (value['loopEnabled'] and (start is None or end is None))):
        raise ValueError('Set B after A to save a practice loop.')
    return value


class PracticeSessions:
    def __init__(self, studio):
        self.studio = studio
        self.root = studio.directory / 'Practice'
        self.records_root = self.root / 'sessions'
        self.media_root = self.root / 'media'
        self.records_root.mkdir(parents=True, exist_ok=True)
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.records = {}
        self._load()

    def _load(self):
        for path in self.records_root.glob('*.json'):
            try:
                if path.is_symlink() or path.stat().st_size > 65536:
                    continue
                row = json.loads(path.read_text(encoding='utf-8'))
                identity = row.get('id') if isinstance(row, dict) else None
                if (not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity) or
                        path.stem != identity or type(row.get('schemaVersion')) is not int or row['schemaVersion'] != 1):
                    continue
                row['identity'] = identity_value(row['identity'])
                row['settings'] = settings_value(row['settings'])
                if not isinstance(row['title'], str) or not 0 < len(row['title']) <= 500:
                    continue
                if type(row['updatedAt']) not in (int, float) or not math.isfinite(row['updatedAt']):
                    continue
                original = row['original']
                if not isinstance(original, dict) or type(original.get('owned')) is not bool:
                    continue
                original['fingerprint'] = identity_value(original['fingerprint'])
                if not isinstance(original.get('path'), str) or original['path'] != original['fingerprint'][0]:
                    continue
                if original['owned'] and not self._owned_path(identity, Path(original['path'])):
                    continue
                analysis = row.get('analysisId')
                if analysis is not None and (not isinstance(analysis, str) or not ANALYSIS_ID.fullmatch(analysis)):
                    continue
                self.records[identity] = row
                if original['owned'] and self._valid_original(row):
                    studio_key = row['identity']
                    self.studio.associate_source_identity(studio_key, original['path'])
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, RecursionError):
                continue

    def _owned_path(self, identity, path):
        folder = self.media_root / identity
        return (not path.is_symlink() and not folder.is_symlink() and
                path.parent.resolve() == folder.resolve() and path.name.startswith('Recording.') and
                path.resolve().is_relative_to(self.media_root.resolve()))

    def _write(self, row):
        target = self.records_root / (row['id'] + '.json')
        temporary = self.records_root / ('.' + row['id'] + '-' + uuid.uuid4().hex + '.new')
        try:
            temporary.write_text(json.dumps(row, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def _origin(self, required=False):
        with self.studio.lock:
            source = self.studio.source
            revision = self.studio.source_revision
            if source is None:
                if required:
                    raise ValueError('Open a recording before saving practice.')
                return None
            try:
                manager = self.studio.stems
                job = manager.selected_job() if manager else ''
                if job:
                    key = manager.recording_identity(job)
                    original = manager.recording_source(job)
                    title = next(item['sourceName'] for item in manager.snapshot()['sessions'] if item['jobId'] == job)
                    return key, original, title, False, revision
                return self.studio.source_identity(source), source, self.studio.name, self.studio.imported, revision
            except (OSError, ValueError, StopIteration):
                if required:
                    raise ValueError('The original recording is missing. Open it again before saving practice.') from None
                return None

    def _piano_job(self, key):
        manager = self.studio.stems
        if manager is None:
            return None
        with self.studio.lock:
            # Avoid rebuilding the complete public stem history for every
            # saved-practice row in a snapshot.
            for identity, session in reversed(list(manager.sessions.items())):
                if session['value'].get('mode') != 'piano':
                    continue
                try:
                    if manager.recording_identity(identity) == key:
                        manager.file(identity, 'piano')
                        manager.file(identity, 'accompaniment')
                        manager.recording_source(identity)
                        return identity
                except (OSError, ValueError):
                    continue
        return None

    def _valid_original(self, row):
        try:
            return fingerprint(row['original']['path']) == tuple(row['original']['fingerprint'])
        except (OSError, ValueError, RuntimeError):
            return False

    def _available(self, row):
        return bool(self._piano_job(row['identity'])) or self._valid_original(row)

    def _public(self, row):
        return {'id': row['id'], 'recordingId': recording_id(row['identity']), 'title': row['title'],
                'updatedAt': row['updatedAt'], 'settings': dict(row['settings']),
                'pianoJobId': self._piano_job(row['identity']), 'available': self._available(row)}

    def _live_result(self, key):
        with self.studio.lock:
            if self.studio.result_identity == key:
                return self.studio.state['result']
            return self.studio.analysis_results.get(key)

    def _guide(self, key, row):
        result = self._live_result(key)
        if result is None and row is not None and self._available(row):
            identity = row.get('analysisId')
            if identity:
                result = self.studio.store.load(identity)
        if not isinstance(result, dict) or not result.get('analysis_id'):
            return None
        return {'analysisId': result['analysis_id'], 'chords': result['chords'],
                'key': result.get('key'), 'tempo_bpm': result.get('tempo_bpm'),
                'duration': result.get('duration')}

    def snapshot(self):
        with self.lock:
            # Read the origin and revision together, including an empty Studio.
            with self.studio.lock:
                revision = self.studio.source_revision
                origin = self._origin()
            key = origin[0] if origin else None
            current = next((row for row in self.records.values() if row['identity'] == key), None)
            return {'sessions': [self._public(row) for row in sorted(self.records.values(), key=lambda row: row['updatedAt'], reverse=True)],
                    'current': self._public(current) if current else None,
                    'sourceRevision': revision, 'recordingId': recording_id(key) if key else None,
                    'pianoJobId': self._piano_job(key) if key else None,
                    'guide': self._guide(key, current) if key else None}

    def remember_analysis(self, key, result):
        analysis = result.get('analysis_id') if isinstance(result, dict) else None
        if not isinstance(analysis, str) or not ANALYSIS_ID.fullmatch(analysis):
            return
        with self.lock:
            for row in self.records.values():
                if row['identity'] == key and row.get('analysisId') != analysis:
                    row['analysisId'] = analysis
                    self._write(row)

    def save(self, body):
        settings = settings_value(body)
        if type(body.get('sourceRevision')) is not int:
            raise ValueError('The recording changed. Try saving practice again.')
        with self.lock:
            with self.studio.lock:
                if self.studio.closed or body['sourceRevision'] != self.studio.source_revision:
                    raise ValueError('The recording changed. Try saving practice again.')
                key, original, title, imported, _ = self._origin(required=True)
                existing = next((row for row in self.records.values() if row['identity'] == key), None)
                supplied = body.get('sessionId')
                if supplied is not None and (not isinstance(supplied, str) or not IDENTIFIER.fullmatch(supplied) or
                                             supplied not in self.records or self.records[supplied]['identity'] != key):
                    raise ValueError('Choose a saved practice session for this recording.')
                if supplied is not None:
                    existing = self.records[supplied]
                if settings['mode'] != 'original' and not self._piano_job(key):
                    raise ValueError('Prepare the piano part before saving this listening mode.')
                identity = existing['id'] if existing else uuid.uuid4().hex
                stream = original.open('rb') if imported and (not existing or not self._valid_original(existing)) else None
                before = None
                if stream:
                    stat = os.fstat(stream.fileno())
                    before = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
                    if self.studio.source_identity(original, stat) != key:
                        stream.close()
                        raise ValueError('The recording changed. Try saving practice again.')
                    original_stamp = (str(original.resolve()), *before)
                else:
                    original_stamp = fingerprint(original)
                    if self.studio.analysis_aliases.get(original_stamp, original_stamp) != key:
                        raise ValueError('The recording changed. Try saving practice again.')
                result = self._live_result(key)
            pending = None
            try:
                if stream:
                    suffix = original.suffix if re.fullmatch(r'\.[a-zA-Z0-9]{1,12}', original.suffix) else '.media'
                    folder = self.media_root / identity
                    folder.mkdir(exist_ok=True)
                    if folder.is_symlink():
                        raise ValueError('The saved practice folder is invalid.')
                    pending = folder / ('.pending-' + uuid.uuid4().hex)
                    target = folder / ('Recording' + suffix)
                    total = 0
                    with stream, pending.open('xb') as copied:
                        while block := stream.read(1024 * 1024):
                            if self.studio.closed:
                                raise ValueError('Studio is closing. Practice could not be saved.')
                            total += len(block)
                            if total > MAX_BYTES or shutil.disk_usage(folder).free < 128 * 1024 ** 2:
                                raise ValueError('Free more storage before saving this recording for practice.')
                            copied.write(block)
                        stat = os.fstat(stream.fileno())
                        if before != (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns):
                            raise ValueError('The recording changed while practice was being saved. Try again.')
                    pending.replace(target)
                    original_stamp = fingerprint(target)
                    original_info = {'path': str(target.resolve()), 'owned': True, 'fingerprint': original_stamp}
                    self.studio.associate_source_identity(key, target)
                elif existing:
                    original_info = dict(existing['original'])
                else:
                    original_info = {'path': original_stamp[0], 'owned': False, 'fingerprint': original_stamp}
                row = {'schemaVersion': 1, 'id': identity, 'identity': key,
                       'title': str(title or original.name)[:500], 'original': original_info,
                       'settings': settings, 'updatedAt': time.time(),
                       'analysisId': result.get('analysis_id') if result else existing.get('analysisId') if existing else None}
                self._write(row)
                self.records[identity] = row
                return dict(self.snapshot(), saved=self._public(row))
            except Exception:
                if not existing and stream:
                    shutil.rmtree(self.media_root / identity, ignore_errors=True)
                raise
            finally:
                if stream:
                    stream.close()
                if pending:
                    pending.unlink(missing_ok=True)

    def open(self, body):
        identity = body.get('id')
        if not isinstance(identity, str) or not IDENTIFIER.fullmatch(identity):
            raise ValueError('Choose a saved practice session.')
        with self.lock:
            row = self.records.get(identity)
            if row is None:
                raise ValueError('This saved practice session is unavailable.')
            job = self._piano_job(row['identity'])
            settings = dict(row['settings'])
            notice = None
            with self.studio.lock:
                revision = body.get('sourceRevision')
                if revision is not None and (type(revision) is not int or revision != self.studio.source_revision):
                    raise ValueError('The recording changed. Choose the saved practice session again.')
                if self.studio.closed:
                    raise ValueError('Studio is closing.')
                if job:
                    stem = {'original': 'source', 'piano': 'piano', 'backing': 'accompaniment'}[settings['mode']]
                    self.studio.stems.select(job, stem)
                elif self._valid_original(row):
                    self.studio.associate_source_identity(row['identity'], row['original']['path'])
                    self.studio.select_source(row['original']['path'], row['title'])
                    if settings['mode'] != 'original':
                        settings['mode'] = 'original'
                        notice = 'The saved piano tracks are unavailable. Opened the original recording.'
                else:
                    raise ValueError('The saved recording is missing or has changed. Open the recording again to start a new practice session.')
            return dict(self.snapshot(), opened=self._public(row), settings=settings, notice=notice)
