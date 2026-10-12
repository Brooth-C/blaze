"""Local history, durable manual corrections, portable exports, and bounded cache."""
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from .chords import normalize, transpose, estimate_key


def validate(result):
    if result.get('schema_version') != 1:
        raise ValueError('Unsupported Music Studio result version.')
    duration = result.get('duration')
    if not isinstance(duration, (float, int)) or not math.isfinite(duration) or not 0 < duration <= 7200:
        raise ValueError('Invalid recording duration.')
    events = result.get('chords')
    if not isinstance(events, list) or not 0 < len(events) <= 100000:
        raise ValueError('Invalid chord timeline.')
    end = 0.0
    for event in events:
        start, following = event['start'], event['end']
        if not math.isfinite(start) or not math.isfinite(following) or abs(start - end) > 1e-6 or not start < following <= duration + 1e-6:
            raise ValueError('Chord timestamps must cover the recording without gaps or overlaps.')
        event['chord'] = normalize(event['chord'])
        score = event.get('model_score')
        if score is not None and (not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('Invalid model score.')
        end = following
    if abs(end - duration) > 1e-6:
        raise ValueError('The chord timeline does not cover the recording.')
    return result


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.cache = self.directory / 'analyses'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._db() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS corrections (analysis TEXT, start REAL, end REAL, chord TEXT NOT NULL, PRIMARY KEY(analysis,start,end))')
            connection.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS rhythm (source TEXT PRIMARY KEY, value TEXT NOT NULL)')

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.directory / 'studio.sqlite3')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def identity(result):
        data = result['source_sha256'] + result['model']['sha256'] + result['model']['frontend_sha256'] + ':schema1:edgepad1'
        return hashlib.sha256(data.encode()).hexdigest()

    def save(self, result):
        validate(result)
        identity = self.identity(result)
        result['analysis_id'] = identity
        with self.lock:
            target = self.cache / (identity + '.json')
            temporary = target.with_suffix('.new')
            try:
                with temporary.open('w', encoding='utf-8') as stream:
                    json.dump(result, stream, ensure_ascii=False, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            self.prune(target)
        return self.apply_corrections(result)

    def load(self, identity):
        if len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('Invalid analysis identifier.')
        with self.lock:
            path = self.cache / (identity + '.json')
            if not path.is_file() or path.stat().st_size > 16 * 1024 ** 2:
                return None
            try:
                result = validate(json.loads(path.read_text(encoding='utf-8')))
            except (OSError, ValueError, KeyError, TypeError):
                return None
            if self.identity(result) != identity:
                return None
            os.utime(path, None)
            return self.apply_corrections(result)

    def apply_corrections(self, result):
        result = json.loads(json.dumps(result))
        identity = self.identity(result)
        result['analysis_id'] = identity
        with self._db() as connection:
            corrections = {(start, end): chord for start, end, chord in connection.execute('SELECT start,end,chord FROM corrections WHERE analysis=?', (identity,))}
        changed = False
        for event in result['chords']:
            label = corrections.get((event['start'], event['end']))
            if label is not None:
                event['original_chord'] = event.get('original_chord', event['chord'])
                event['chord'] = normalize(label)
                event['edited'] = True
                event['model_score'] = None
                changed = True
        if changed:
            result['key'] = estimate_key(result['chords'])
        with self._db() as connection:
            row = connection.execute('SELECT value FROM rhythm WHERE source=?', (result['source_sha256'],)).fetchone()
        result['rhythm_correction'] = json.loads(row[0]) if row else None
        return result

    def edit_rhythm(self, result, correction):
        validate(result)
        if correction is not None:
            if not isinstance(correction, dict) or correction.get('mode') not in ('unknown', 'beats', 'grid'):
                raise ValueError('Choose a rhythm grid mode.')
            num, den, offset = correction.get('numerator'), correction.get('denominator'), correction.get('offset')
            if type(num) is not int or not 1 <= num <= 12 or den not in (2, 4, 8, 16):
                raise ValueError('Choose a supported time signature.')
            if not isinstance(offset, (float, int)) or not math.isfinite(offset) or not 0 <= offset < result['duration']:
                raise ValueError('Choose a downbeat inside the recording.')
            bpm = correction.get('bpm')
            if correction['mode'] == 'grid' and (not isinstance(bpm, (int, float)) or not math.isfinite(bpm) or not 20 <= bpm <= 300):
                raise ValueError('Enter a BPM between 20 and 300.')
            if correction['mode'] == 'beats' and len(result.get('beats', [])) < 2:
                raise ValueError('No usable detected beat map. Choose a manual tempo grid.')
            changes = correction.get('changes', [])
            if not isinstance(changes, list) or len(changes) > 100:
                raise ValueError('Too many meter changes.')
            previous = offset
            for change in changes:
                t = change.get('time')
                if not isinstance(t, (int, float)) or not math.isfinite(t) or not previous < t < result['duration'] or type(change.get('numerator')) is not int or not 1 <= change['numerator'] <= 12 or change.get('denominator') not in (2, 4, 8, 16):
                    raise ValueError('Meter changes must have increasing times and valid signatures.')
                previous = t
        with self.lock, self._db() as connection:
            if correction is None:
                connection.execute('DELETE FROM rhythm WHERE source=?', (result['source_sha256'],))
            else:
                connection.execute('INSERT OR REPLACE INTO rhythm VALUES (?,?)', (result['source_sha256'], json.dumps(correction, allow_nan=False)))
        return self.apply_corrections(result)

    def edit(self, result, index, label):
        label = normalize(label)
        validate(result)
        if not isinstance(index, int) or not 0 <= index < len(result['chords']):
            raise ValueError('Choose a chord from this recording.')
        event = result['chords'][index]
        with self.lock, self._db() as connection:
            connection.execute('INSERT OR REPLACE INTO corrections VALUES (?,?,?,?)', (self.identity(result), event['start'], event['end'], label))
        return self.apply_corrections(result)

    def prune(self, keep=None):
        with self.lock:
            files = sorted(self.cache.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
            total = keep.stat().st_size if keep and keep.exists() else 0
            count = int(bool(keep and keep.exists()))
            for path in files:
                if path == keep:
                    continue
                size = path.stat().st_size
                if count >= 128 or total + size > 32 * 1024 ** 2:
                    path.unlink()
                else:
                    total += size
                    count += 1

    def clear_cache(self):
        # Corrections remain separate and survive cache eviction/cleanup.
        with self.lock:
            for path in self.cache.glob('*.json'):
                path.unlink()

    def setting(self, name, value=None):
        with self._db() as connection:
            if value is not None:
                connection.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (name, json.dumps(value)))
                return value
            row = connection.execute('SELECT value FROM settings WHERE name=?', (name,)).fetchone()
            return json.loads(row[0]) if row else None


def export_json(result, amount=0):
    validate(result)
    result = json.loads(json.dumps(result))
    if amount:
        result['transpose_semitones'] = int(amount)
        for event in result['chords']:
            event['original_chord'] = event.get('original_chord', event['chord'])
            event['chord'] = transpose(event['chord'], amount)
    return json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')


def export_csv(result, amount=0):
    validate(result)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['start_seconds', 'end_seconds', 'chord', 'uncalibrated_model_score', 'edited'])
    for event in result['chords']:
        writer.writerow([f"{event['start']:.6f}", f"{event['end']:.6f}", transpose(event['chord'], amount),
                         '' if event['model_score'] is None else f"{event['model_score']:.6f}", bool(event.get('edited'))])
    return stream.getvalue().encode('utf-8')
