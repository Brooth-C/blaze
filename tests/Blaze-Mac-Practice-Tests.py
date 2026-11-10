"""Practice sessions survive restart and stay bound to their original recording."""
import hashlib
import http.client
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.practice_sessions import PracticeSessions
from music_studio.server import Studio, create_server
from music_studio.stem_jobs import StemJobs


def recording():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        audio.writeframes(struct.pack('<hh', 1000, -1000) * (44100 * 2))
    return output.getvalue()


def analysis_for(source):
    return {'schema_version': 1, 'duration': 2, 'analysis_seconds': 1,
            'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'engine_version': 'overlap1', 'key': 'C major', 'tempo_bpm': 120,
            'model': {'name': 'Controlled recognition', 'sha256': 'practice-model',
                      'frontend_sha256': 'practice-frontend'},
            'beats': [0, .5, 1, 1.5], 'chords': [{'start': 0, 'end': 2, 'chord': 'C:maj'}]}


class PianoSeparator:
    def __call__(self, *_):
        return self

    def separate(self, source, folder, progress, cancel_event):
        rows = {}
        for stem in ('piano', 'accompaniment'):
            target = folder / (stem + '.wav')
            target.write_bytes(recording())
            rows[stem] = target
        return rows


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'Original song.wav'
        self.source.write_bytes(recording())
        self.other = self.root / 'Another song.wav'
        self.other.write_bytes(recording() + b'other')
        self.data = self.root / 'state'
        self.studios = []
        self.studio, self.practice = self.make_studio(self.source)

    def tearDown(self):
        for studio in self.studios:
            studio.close()

    def make_studio(self, source=None):
        studio = Studio(self.data, 'ffmpeg', source)
        studio.presentation = 'mac'
        studio.stems = StemJobs(studio, separator_factory=PianoSeparator())
        practice = PracticeSessions(studio)
        studio.practice_sessions = practice
        self.studios.append(studio)
        return studio, practice

    def save(self, **changes):
        body = {'sourceRevision': self.studio.source_revision, 'position': .5, 'rate': .75,
                'loopStart': .2, 'loopEnd': 1.2, 'loopEnabled': True, 'mode': 'original'}
        body.update(changes)
        return self.practice.save(body)

    def prepare_piano(self):
        self.studio.stems.start('piano')
        self.studio.stems.worker.join(timeout=5)
        self.assertEqual(self.studio.stems.snapshot()['status'], 'done')
        return self.studio.stems.snapshot()['jobId']

    def test_original_settings_round_trip_after_process_restart(self):
        answer = self.save()
        saved = answer['saved']
        self.assertEqual(answer['current']['id'], saved['id'])
        self.studio.close()
        next_studio, next_practice = self.make_studio()
        opened = next_practice.open({'id': saved['id']})
        self.assertEqual(next_studio.source, self.source)
        self.assertEqual(opened['settings'], saved['settings'])
        self.assertEqual(opened['current']['recordingId'], answer['recordingId'])
        self.assertIsNone(opened['notice'])

    def test_autosave_reuses_session_and_keeps_paths_private(self):
        first = self.save()
        second = self.save(sessionId=first['saved']['id'], position=.9, rate=1.25)
        third = self.save(position=.7)
        self.assertEqual(first['saved']['id'], second['saved']['id'])
        self.assertEqual(first['saved']['id'], third['saved']['id'])
        self.assertEqual(len(self.practice.snapshot()['sessions']), 1)
        self.assertNotIn(str(self.root), json.dumps(second))
        self.assertEqual(len(second['recordingId']), 64)

    def test_settings_are_validated_before_saving(self):
        for changes in ({'rate': float('nan')}, {'rate': True}, {'rate': 2},
                        {'position': float('inf')}, {'position': -1},
                        {'loopStart': 2, 'loopEnd': 1}, {'loopEnd': None},
                        {'loopEnabled': 'true'}, {'mode': 'voice'}, {'sourceRevision': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.save(**changes)
        self.assertEqual(self.practice.snapshot()['sessions'], [])

    def test_stale_save_open_and_foreign_session_are_rejected(self):
        first = self.save()['saved']
        old_revision = self.studio.source_revision
        self.studio.open_local_file(self.other)
        for action in (lambda: self.save(sourceRevision=old_revision),
                       lambda: self.save(sessionId=first['id']),
                       lambda: self.practice.open({'id': first['id'], 'sourceRevision': old_revision}),
                       lambda: self.practice.open({'id': '../../private'})):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.studio.source, self.other)

    def test_track_switch_cannot_relabel_old_practice_metadata(self):
        job = self.prepare_piano()
        before = self.practice.snapshot()
        origin = self.practice._origin

        def switch_after_reading_origin():
            value = origin()
            self.studio.open_local_file(self.other)
            return value

        with patch.object(self.practice, '_origin', side_effect=switch_after_reading_origin):
            answer = self.practice.snapshot()
        self.assertEqual(answer['recordingId'], before['recordingId'])
        self.assertEqual(answer['pianoJobId'], job)
        self.assertEqual(answer['sourceRevision'], before['sourceRevision'])
        self.assertNotEqual(answer['sourceRevision'], self.studio.source_revision)

    def test_imported_audio_is_retained_when_switching_during_save(self):
        imported = self.studio.incoming / 'upload.wav'
        data = recording()
        imported.write_bytes(data)
        self.studio.select_source(imported, 'My recording.wav', imported=True)
        actual_open = Path.open
        switched = False
        studio = self.studio
        other = self.other

        class PinnedReader:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

            def close(self):
                self.wrapped.close()

            def fileno(self):
                return self.wrapped.fileno()

            def read(self, amount):
                nonlocal switched
                if not switched:
                    switched = True
                    studio.open_local_file(other)
                return self.wrapped.read(amount)

        def open_file(path, mode='r', *args, **kwargs):
            result = actual_open(path, mode, *args, **kwargs)
            return PinnedReader(result) if path == imported and mode == 'rb' else result

        with patch.object(Path, 'open', open_file):
            saved = self.save()
        self.assertFalse(imported.exists())
        self.assertIsNone(saved['current'], 'A late save changed the active recording')
        identity = saved['saved']['id']
        self.studio.close()
        next_studio, next_practice = self.make_studio()
        next_practice.open({'id': identity})
        self.assertEqual(next_studio.source.read_bytes(), data)
        self.assertEqual(next_studio.imported, False)

    def test_native_original_changed_or_missing_does_not_restore_old_practice(self):
        saved = self.save()['saved']
        self.source.write_bytes(b'a revised mix')
        self.assertFalse(self.practice.snapshot()['sessions'][0]['available'])
        with self.assertRaisesRegex(ValueError, 'missing or has changed'):
            self.practice.open({'id': saved['id']})
        self.source.unlink()
        self.assertFalse(self.practice.snapshot()['sessions'][0]['available'])

    def test_original_piano_backing_share_identity_and_restore_saved_mode(self):
        before = self.practice.snapshot()['recordingId']
        job = self.prepare_piano()
        for stem in ('source', 'piano', 'accompaniment'):
            self.studio.stems.select(job, stem)
            self.assertEqual(self.practice.snapshot()['recordingId'], before)
            self.assertEqual(self.practice.snapshot()['pianoJobId'], job)
        saved = self.save(mode='backing')['saved']
        self.studio.close()
        next_studio, next_practice = self.make_studio()
        opened = next_practice.open({'id': saved['id']})
        self.assertEqual(opened['settings']['mode'], 'backing')
        self.assertEqual(next_studio.stems.selected_stem(), 'accompaniment')
        self.assertEqual(opened['recordingId'], before)

    def test_missing_piano_outputs_fall_back_to_known_original(self):
        job = self.prepare_piano()
        saved = self.save(mode='piano')['saved']
        self.studio.stems.file(job, 'piano').unlink()
        opened = self.practice.open({'id': saved['id']})
        self.assertEqual(opened['settings']['mode'], 'original')
        self.assertIn('original', opened['notice'])
        self.assertEqual(self.studio.source.read_bytes(), self.source.read_bytes())

    def test_completed_analysis_is_saved_and_restored_without_running_models(self):
        saved = self.save()['saved']
        bundle = SimpleNamespace(structured=False, metadata={'sha256': 'practice-model'},
                                 manifest={'frontend': {'sha256': 'practice-frontend'}})

        class Recognition:
            def __init__(self, *_):
                pass

            def check(self):
                pass

            def cancel(self):
                pass

            def analyze(self, source, progress):
                return analysis_for(source)

        with patch('music_studio.server.ModelBundle', return_value=bundle), \
                patch('music_studio.server.Analyzer', Recognition):
            self.studio.analyze('powerful')
            self.studio.worker.join(timeout=5)
        self.assertEqual(self.studio.state['analysisTask']['status'], 'done')
        analysis = self.studio.state['result']['analysis_id']
        self.assertEqual(self.practice.snapshot()['guide']['analysisId'], analysis)
        self.studio.close()
        _, next_practice = self.make_studio()
        with patch('music_studio.server.ModelBundle', side_effect=AssertionError('No model rerun')):
            restored = next_practice.open({'id': saved['id']})
        self.assertEqual(restored['guide']['analysisId'], analysis)
        self.assertEqual(restored['guide']['chords'][0]['chord'], 'C:maj')
        self.assertNotIn('waveform', restored['guide'])

    def test_selected_stem_analysis_does_not_replace_original_guide(self):
        job = self.prepare_piano()
        original = self.studio.store.save(analysis_for(self.source))
        key = self.studio.stems.recording_identity(job)
        self.studio.remember_analysis(key, original)
        self.save()
        self.studio.stems.select(job, 'piano')
        different = dict(original, key='F major', chords=[{'start': 0, 'end': 2, 'chord': 'F:maj'}])
        self.studio.result_identity = self.studio.source_identity(self.studio.source)
        self.studio.state['result'] = different
        self.assertEqual(self.practice.snapshot()['guide']['key'], 'C major')

    def test_invalid_persisted_records_do_not_open_external_owned_paths(self):
        saved = self.save()['saved']
        metadata = self.practice.records_root / (saved['id'] + '.json')
        row = json.loads(metadata.read_text())
        row['original']['owned'] = True
        metadata.write_text(json.dumps(row))
        _, next_practice = self.make_studio()
        self.assertEqual(next_practice.snapshot()['sessions'], [])
        with self.assertRaises(ValueError):
            next_practice.open({'id': saved['id']})

    def test_client_cannot_supply_recording_paths_or_analysis_identifiers(self):
        saved = self.save(original={'path': str(self.other)}, analysisId='a' * 64)
        row = self.practice.records[saved['saved']['id']]
        self.assertEqual(row['original']['path'], str(self.source))
        self.assertIsNone(row['analysisId'])
        self.assertIsNone(saved['guide'])

    def test_authentication_origin_and_mac_boundary(self):
        server = create_server(self.studio)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)

        def request(path, body=None, token=True, origin=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Blaze-Token': self.studio.token} if token else {}
            if origin:
                headers['Origin'] = origin
            payload = json.dumps(body) if body is not None else None
            connection.request('POST' if body is not None else 'GET', path, payload, headers)
            response = connection.getresponse()
            value = json.loads(response.read())
            connection.close()
            return response.status, value

        self.assertEqual(request('/api/practice', token=False)[0], 403)
        self.assertEqual(request('/api/practice', origin='https://untrusted.example')[0], 403)
        self.assertEqual(request('/api/practice')[0], 200)
        self.assertEqual(request('/api/practice-save', {'sourceRevision': 0})[0], 200)
        identity = self.practice.snapshot()['current']['id']
        self.assertEqual(request('/api/practice-open', {'id': identity})[0], 200)
        self.studio.presentation = 'desktop'
        self.assertEqual(request('/api/practice')[0], 404)
        self.assertEqual(request('/api/practice-save', {'sourceRevision': 0})[0], 404)


if __name__ == '__main__':
    unittest.main()
