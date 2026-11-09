"""Stem job lifecycle and authenticated HTTP/file ownership contracts.

The separator is controlled here; real SCNet inference is checked separately.
"""
import http.client
from email.message import Message
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.parse import urlencode
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio, create_server
from music_studio.stem_jobs import STEMS, StemJobs


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        audio.writeframes(struct.pack('<hh', 1000, -1000) * 128)
    return output.getvalue()


class ControlledSeparator:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.mode = 'success'
        self.output = None

    def __call__(self, _models, _ffmpeg):
        return self

    def separate(self, source, output_dir, progress, cancel_event):
        self.output = output_dir
        self.source_bytes = source.read_bytes()
        (output_dir / 'partial').write_bytes(b'incomplete work')
        progress(.25, 'Separating the recording…')
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError('Controlled test worker did not resume.')
        if cancel_event.is_set():
            raise ValueError('cancelled')
        if self.mode == 'failure':
            raise ValueError('The decoder could not read this recording.')
        outputs = {}
        for stem in getattr(self, 'stems', STEMS):
            path = output_dir / (stem + '.wav')
            path.write_bytes(wav_bytes())
            outputs[stem] = path
        if self.mode == 'outside':
            outputs['vocals'] = source
        elif self.mode == 'missing':
            outputs.pop('vocals')
        (output_dir / 'partial').unlink()
        return outputs


class StemJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'My recording.wav'
        self.source.write_bytes(wav_bytes())
        self.studio = Studio(self.root / 'data', 'ffmpeg', self.source)
        self.studio.presentation = 'mac'
        self.separator = ControlledSeparator()
        self.jobs = StemJobs(self.studio, separator_factory=self.separator)
        self.studio.stems = self.jobs
        self.server = create_server(self.studio)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self):
        self.separator.release.set()
        self.studio.close()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(3)
        self.temp.cleanup()

    def request(self, path, body=None, token=True, headers=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            outgoing = {'X-Blaze-Token': self.studio.token} if token else {}
            outgoing.update(headers or {})
            payload = raw if raw is not None else json.dumps(body) if body is not None else None
            connection.request('POST' if body is not None or raw is not None else 'GET', path,
                               body=payload, headers=outgoing)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def start(self):
        status, _, payload = self.request('/api/stems-start', {})
        self.assertEqual(status, 200, payload)
        self.assertTrue(self.separator.started.wait(2))
        return json.loads(payload)['jobId']

    def finish(self):
        self.separator.release.set()
        self.jobs.worker.join(3)
        self.assertFalse(self.jobs.worker.is_alive())
        return self.jobs.snapshot()

    def test_five_mode_exports_five_individual_instruments(self):
        self.separator.stems = ('vocals','drums','bass','piano','other')
        status, _, body = self.request('/api/stems-start', {'mode':'five'})
        self.assertEqual(status, 200, body)
        state = self.finish()
        self.assertEqual(state['mode'], 'five')
        self.assertEqual(state['status'], 'done')
        self.assertEqual({s['id'] for s in state['stems']},set(self.separator.stems))
        query='?jobId='+state['jobId']+'&stem='
        for stem in self.separator.stems:
            self.assertEqual(self.request('/api/stem-file'+query+stem)[0],200)
        self.assertEqual(self.request('/api/stem-file'+query+'accompaniment')[0],400)
        self.assertTrue(self.source.exists())

    def test_piano_mode_exports_only_its_two_completed_tracks(self):
        self.separator.stems = ('piano', 'accompaniment')
        status, _, body = self.request('/api/stems-start', {'mode':'piano'})
        self.assertEqual(status, 200, body)
        state = self.finish()
        self.assertEqual(state['mode'], 'piano')
        self.assertEqual(state['status'], 'done')
        self.assertEqual({s['id'] for s in state['stems']}, {'piano','accompaniment'})
        query = '?jobId=' + state['jobId'] + '&stem='
        self.assertEqual(self.request('/api/stem-file' + query + 'piano')[0], 200)
        self.assertEqual(self.request('/api/stem-file' + query + 'vocals')[0], 400)
        status, _, _ = self.request('/api/stems-select', {'jobId':state['jobId'], 'stem':'piano'})
        self.assertEqual(status, 200)
        self.assertEqual(self.studio.name, 'Piano.wav')
        self.assertTrue(self.source.is_file())

    def test_piano_request_dispatches_native_model_in_background(self):
        self.jobs.separator_factory = None
        self.jobs.models = self.root / 'model-dispatch'
        self.jobs.models.mkdir()
        (self.jobs.models / 'manifest.json').write_text('{}')
        self.separator.stems = ('piano', 'accompaniment')
        with patch.dict('os.environ', {'BLAZE_PIANO_BACKEND':'onnx'}), \
             patch('music_studio.native_piano.NativePianoSeparator', return_value=self.separator) as native, \
             patch('music_studio.piano.PianoSeparator', side_effect=AssertionError('Legacy piano path selected')):
            status, _, body = self.request('/api/stems-start', {'mode': 'piano'})
            self.assertEqual(status, 200, body)
            state = self.finish()
            self.assertEqual(state['status'], 'done')
            native.assert_called_once_with(self.jobs.models, self.studio.ffmpeg, runtime_backend='cpu')
        self.assertEqual({row['id'] for row in state['stems']}, {'piano', 'accompaniment'})

    def test_nine_mode_exports_only_its_owned_instrument_tracks(self):
        self.separator.stems = ('vocals', 'drums', 'bass', 'piano', 'guitar', 'strings', 'brass', 'synths', 'other')
        status, _, body = self.request('/api/stems-start', {'mode': 'nine'})
        self.assertEqual(status, 200, body)
        state = self.finish()
        self.assertEqual(state['mode'], 'nine')
        self.assertEqual(state['status'], 'done')
        self.assertEqual({row['id'] for row in state['stems']}, set(self.separator.stems))
        for name in self.separator.stems:
            query = '?jobId=' + state['jobId'] + '&stem=' + name
            self.assertEqual(self.request('/api/stem-file' + query)[0], 200)
        self.assertEqual(self.request('/api/stem-file?jobId=' + state['jobId'] + '&stem=violin')[0], 400)
        self.assertTrue(self.source.is_file())

    def test_unhashable_or_unknown_modes_are_rejected(self):
        for mode in ([], {}, None, 12, 'guitar'):
            with self.subTest(mode=mode):
                self.assertEqual(self.request('/api/stems-start', {'mode': mode})[0], 400)

    def test_success_exports_exact_saved_audio_and_selects_without_deleting_user_file(self):
        identity = self.start()
        state = self.finish()
        self.assertEqual(state['status'], 'done')
        self.assertEqual({row['id'] for row in state['stems']}, set(STEMS))
        self.assertFalse(self.studio.state['busy'])
        self.assertFalse((self.jobs.root / ('.' + identity)).exists())
        for stem in STEMS:
            status, headers, payload = self.request('/api/stem-file?jobId=' + identity + '&stem=' + stem)
            self.assertEqual(status, 200)
            self.assertEqual(payload, wav_bytes())
            self.assertEqual(headers['Content-Type'], 'audio/wav')
            disposition = Message()
            disposition['Content-Disposition'] = headers['Content-Disposition']
            self.assertEqual(disposition.get_filename(), stem.title() + '.wav')
        self.studio.state['result'] = {'previous': 'chords'}
        status, _, payload = self.request('/api/stems-select', {'jobId': identity, 'stem': 'vocals'})
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.studio.source, self.jobs.files['vocals'])
        self.assertEqual(self.studio.source_revision, 1)
        self.assertIsNone(self.studio.state['result'])
        self.assertFalse(self.studio.imported)
        self.assertTrue(self.source.exists())
        status, _, media = self.request('/media?sourceRevision=1')
        self.assertEqual(status, 200)
        self.assertEqual(media, wav_bytes())

    def test_original_can_be_reopened_after_selecting_a_stem_and_importing(self):
        payload = wav_bytes()
        self.assertEqual(self.request('/api/import', raw=payload,
                                      headers={'X-File-Name': 'Original song.wav'})[0], 200)
        uploaded = self.studio.source
        identity = self.start()
        state = self.finish()
        self.assertEqual(len(state['sessions']), 1)
        self.assertEqual(state['sessions'][0]['original']['filename'], 'Original song.wav')
        original = self.jobs.file(identity, 'source')
        self.assertEqual(original.read_bytes(), payload)
        self.assertNotEqual(original, uploaded)
        self.assertEqual(self.jobs.selected_job(), identity)
        self.assertEqual(self.jobs.selected_stem(), 'source')
        self.assertEqual(self.request('/api/stems-select', {'jobId': identity, 'stem': 'vocals'})[0], 200)
        self.assertFalse(uploaded.exists(), 'Only the obsolete incoming upload is removed.')
        self.assertTrue(original.exists())
        self.assertEqual(self.request('/api/stems-select', {'jobId': identity, 'stem': 'source'})[0], 200)
        self.assertEqual(self.studio.source, original)
        self.assertEqual(self.studio.name, 'Original song.wav')
        self.assertEqual(self.jobs.selected_stem(), 'source')
        status, _, data = self.request('/api/stem-file?jobId=' + identity + '&stem=source')
        self.assertEqual(status, 200)
        self.assertEqual(data, payload)
        self.assertNotIn(str(self.root), json.dumps(self.jobs.snapshot()))

    def test_original_video_keeps_filename_and_media_kind(self):
        video = self.root / 'Live set.mp4'
        video.write_bytes(wav_bytes())
        self.studio.open_local_file(video)
        identity = self.start()
        self.finish()
        self.jobs.select(identity, 'vocals')
        self.jobs.select(identity, 'source')
        self.assertEqual(self.studio.name, 'Live set.mp4')
        self.assertEqual(self.studio.state['mediaKind'], 'video')
        self.assertEqual(self.jobs.file(identity, 'source').suffix, '.mp4')
        self.assertEqual(self.jobs.descriptor(identity, 'source')['mediaKind'], 'video')
        status, headers, _ = self.request('/api/stem-file?jobId=' + identity + '&stem=source')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'video/mp4')

    def test_discovery_title_original_keeps_the_actual_media_extension(self):
        for suffix, content_type, kind in (('.m4a', 'audio/mp4', 'audio'), ('.mp4', 'video/mp4', 'video')):
            with self.subTest(suffix=suffix):
                # Metadata/export contract; the controlled separator does not decode.
                source = self.root / ('downloaded-media' + suffix)
                source.write_bytes(wav_bytes())
                self.studio.select_source(source, 'Acoustic Session')
                identity = self.start()
                state = self.finish()
                filename = 'Acoustic Session' + suffix
                self.assertEqual(state['sourceName'], 'Acoustic Session')
                self.assertEqual(state['sessions'][0]['original']['filename'], filename)
                self.jobs.select(identity, 'source')
                self.assertEqual(self.studio.name, filename)
                self.assertEqual(self.studio.state['mediaKind'], kind)
                status, headers, payload = self.request('/api/stem-file?jobId=' + identity + '&stem=source')
                self.assertEqual(status, 200)
                self.assertEqual(payload, wav_bytes())
                self.assertEqual(headers['Content-Type'], content_type)
                disposition = Message()
                disposition['Content-Disposition'] = headers['Content-Disposition']
                self.assertEqual(disposition.get_filename(), filename)

    def test_previous_completed_session_survives_new_failure_and_cancellation(self):
        identity = self.start()
        self.finish()
        saved = self.jobs.file(identity, 'vocals')
        for outcome in ('failure', 'cancel'):
            with self.subTest(outcome=outcome):
                self.separator = ControlledSeparator()
                self.jobs.separator_factory = self.separator
                self.separator.mode = 'failure' if outcome == 'failure' else 'success'
                self.start()
                self.assertEqual(self.jobs.file(identity, 'vocals'), saved)
                self.jobs.select(identity, 'source')
                if outcome == 'cancel':
                    self.jobs.cancel()
                self.assertEqual(self.finish()['status'], 'cancelled' if outcome == 'cancel' else 'failed')
                self.assertEqual(self.jobs.file(identity, 'vocals').read_bytes(), wav_bytes())
                self.jobs.select(identity, 'vocals')
                self.assertEqual(self.jobs.selected_job(), identity)
                self.assertEqual(len(self.jobs.snapshot()['sessions']), 1)

    def restored_jobs(self, initial=None):
        restored = Studio(self.studio.directory, 'ffmpeg', initial)
        restored.presentation = 'mac'
        restored.stems = StemJobs(restored, separator_factory=self.separator)
        self.addCleanup(restored.close)
        return restored, restored.stems

    def test_completed_piano_pair_and_original_restore_without_model_work(self):
        self.separator.stems = ('piano', 'accompaniment')
        self.jobs.start('piano')
        state = self.finish()
        identity = state['jobId']
        key = self.jobs.recording_identity(identity)
        self.assertTrue((self.jobs.root / identity / 'session.json').is_file())
        restored, jobs = self.restored_jobs(self.source)
        self.assertEqual(jobs.snapshot()['status'], 'done')
        self.assertEqual(jobs.snapshot()['mode'], 'piano')
        self.assertIsNone(jobs.snapshot()['sessions'][0]['sourceRevision'])
        self.assertIsNone(jobs.worker, 'Restoring a pair must not rerun its model')
        self.assertEqual(jobs.recording_identity(identity), key)
        self.assertEqual(jobs.selected_job(), identity)
        self.assertEqual(jobs.selected_stem(), 'source')
        for stem in ('piano', 'accompaniment', 'source'):
            jobs.select(identity, stem)
            self.assertEqual(restored.source.read_bytes(), wav_bytes())
            self.assertEqual(jobs.selected_stem(), stem)
        self.assertEqual(restored.source_identity(jobs.recording_source(identity)), key)
        self.assertNotIn(str(self.root), json.dumps(jobs.snapshot()))

    def test_imported_original_stays_recoverable_after_app_restart(self):
        self.request('/api/import', raw=wav_bytes(), headers={'X-File-Name': 'Learning song.wav'})
        uploaded = self.studio.source
        identity = self.start()
        self.finish()
        self.jobs.select(identity, 'vocals')
        self.assertFalse(uploaded.exists())
        restored, jobs = self.restored_jobs()
        jobs.select(identity, 'source')
        self.assertEqual(restored.name, 'Learning song.wav')
        self.assertEqual(restored.source.read_bytes(), wav_bytes())
        self.assertEqual(restored.source_identity(restored.source), jobs.recording_identity(identity))

    def test_symlinked_data_directory_keeps_waveform_ownership_paths_consistent(self):
        from music_studio.waveform import selection
        alias = self.root / 'data-alias'
        try:
            alias.symlink_to(self.studio.directory, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable')
        alternate = Studio(alias, 'ffmpeg', self.source)
        alternate.presentation = 'mac'
        self.addCleanup(alternate.close)
        separator = ControlledSeparator()
        separator.stems = ('piano', 'accompaniment')
        separator.release.set()
        jobs = alternate.stems = StemJobs(alternate, separator_factory=separator)
        identity = jobs.start('piano')['jobId']
        jobs.worker.join(3)
        self.assertEqual(jobs.snapshot()['status'], 'done')
        jobs.select(identity, 'piano')
        source, valid, owned = selection(alternate, str(alternate.source_revision), identity, 'source')
        self.assertEqual(owned, identity)
        self.assertEqual(source, jobs.sessions[identity]['files']['source'])
        self.assertTrue(valid(), 'Filesystem aliases invalidated the waveform immediately')

    def test_changed_native_recording_does_not_reuse_persisted_pair(self):
        identity = self.start()
        self.finish()
        self.source.write_bytes(wav_bytes() + b'changed recording')
        restored, jobs = self.restored_jobs(self.source)
        self.assertEqual(jobs.selected_job(), '')
        self.assertEqual(jobs.selected_stem(), '')
        jobs.select(identity, 'source')
        self.assertEqual(restored.source.read_bytes(), wav_bytes())

    def test_changed_retained_original_is_not_rebound_to_old_recording_identity(self):
        identity = self.start()
        self.finish()
        original = self.jobs.recording_source(identity)
        original.write_bytes(wav_bytes() + b'edited saved original')
        with self.assertRaisesRegex(ValueError, 'original changed'):
            self.jobs.recording_identity(identity)
        _, jobs = self.restored_jobs()
        self.assertEqual(jobs.snapshot()['sessions'], [])

    def test_recording_modified_during_copy_does_not_publish_a_mixed_input(self):
        self.source.write_bytes(wav_bytes() * 4000)
        modified = False
        def free_space(_path):
            nonlocal modified
            if not modified:
                modified = True
                self.source.write_bytes(b'changed in place during source copy')
            return SimpleNamespace(free=10 * 1024 ** 3)
        with patch('music_studio.stem_jobs.shutil.disk_usage', side_effect=free_space):
            self.jobs.start()
            self.jobs.worker.join(3)
        self.assertTrue(modified)
        self.assertEqual(self.jobs.snapshot()['status'], 'failed')
        self.assertIn('recording changed', self.jobs.snapshot()['error'])
        self.assertFalse(self.separator.started.is_set(), 'The model received a changing input')
        self.assertEqual(self.jobs.snapshot()['sessions'], [])
        self.assertEqual(list(self.jobs.root.glob('*/session.json')), [])

    def test_explicit_old_stem_selection_is_not_hijacked_by_later_session(self):
        first = self.start()
        self.finish()
        self.jobs.select(first, 'vocals')
        self.separator.stems = ('piano', 'accompaniment')
        self.jobs.start('piano')
        second = self.finish()['jobId']
        self.assertEqual(self.jobs.selected_job(), second)
        self.jobs.select(first, 'vocals')
        self.assertEqual(self.jobs.selected_job(), first)
        self.assertEqual(self.jobs.selected_stem(), 'vocals')
        _, restored = self.restored_jobs(self.jobs.file(first, 'vocals'))
        self.assertEqual(restored.selected_job(), first)

    def test_saved_session_loader_rejects_corrupt_or_unowned_records(self):
        identity = self.start()
        self.finish()
        sidecar = self.jobs.root / identity / 'session.json'
        original = json.loads(sidecar.read_text())
        cases = []
        for field, value in [('schema_version', 99), ('jobId', '../other'),
                             ('sourceIdentity', ['/tmp/not-an-identity']), ('mode', []),
                             ('sourceName', {}), ('createdAt', True)]:
            value_record = dict(original)
            value_record[field] = value
            cases.append(value_record)
        for value in ('../../My recording.wav', str(self.source), 'original/../vocals.wav'):
            value_record = dict(original, files=dict(original['files'], vocals=value))
            cases.append(value_record)
        value_record = dict(original, files={k: v for k, v in original['files'].items() if k != 'vocals'})
        cases.append(value_record)
        cases.append(dict(original, files=dict(original['files'], vocals=original['files']['drums'])))
        cases.extend(([], None))
        for value in cases:
            with self.subTest(value=value):
                sidecar.write_text(json.dumps(value))
                _, restored = self.restored_jobs()
                self.assertEqual(restored.snapshot()['sessions'], [])
                with self.assertRaises(ValueError):
                    restored.file(identity, 'source')
        sidecar.write_text('{incomplete JSON')
        _, restored = self.restored_jobs()
        self.assertEqual(restored.snapshot()['sessions'], [])

    def test_missing_outputs_and_symlink_escapes_are_not_restored(self):
        identity = self.start()
        self.finish()
        target = self.jobs.file(identity, 'vocals')
        target.unlink()
        _, jobs = self.restored_jobs()
        self.assertEqual(jobs.snapshot()['sessions'], [])
        try:
            target.symlink_to(self.source)
        except OSError:
            self.skipTest('Symlinks unavailable')
        _, jobs = self.restored_jobs()
        self.assertEqual(jobs.snapshot()['sessions'], [])
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.jobs.file(identity, 'vocals')

    def test_failed_metadata_write_does_not_publish_a_partial_session(self):
        self.separator.release.set()
        with patch('music_studio.stem_jobs.os.fsync', side_effect=OSError('disk write failed')):
            identity = self.jobs.start()['jobId']
            self.jobs.worker.join(3)
        self.assertEqual(self.jobs.snapshot()['status'], 'failed')
        self.assertEqual(self.jobs.snapshot()['sessions'], [])
        self.assertEqual(list(self.jobs.root.glob('*/session.json')), [])
        self.assertEqual(list(self.jobs.root.glob('*/.session-*.tmp')), [])
        _, jobs = self.restored_jobs()
        self.assertEqual(jobs.snapshot()['sessions'], [])
        self.assertTrue((self.jobs.root / identity / 'original' / 'Recording.wav').is_file())

    def test_stale_mode_request_cannot_replace_a_newly_opened_recording(self):
        identity = self.start()
        self.finish()
        captured = self.studio.source_revision
        other = self.root / 'Another lesson.wav'
        other.write_bytes(wav_bytes())
        self.studio.open_local_file(other)
        for revision in (captured, True, '0', -1):
            with self.subTest(revision=revision):
                with self.assertRaisesRegex(ValueError, 'recording changed'):
                    self.jobs.select(identity, 'vocals', revision)
                self.assertEqual(self.studio.source, other)
        self.jobs.select(identity, 'vocals', self.studio.source_revision)
        self.assertEqual(self.jobs.selected_stem(), 'vocals')

    def test_real_chord_worker_and_separation_can_run_at_the_same_time(self):
        entered, release = threading.Event(), threading.Event()
        def cached(_identity):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Chord worker did not resume.')
            return {'cached': True}
        self.studio.store.load = cached
        bundle = SimpleNamespace(structured=False, metadata={'sha256': 'model'},
                                 manifest={'frontend': {'sha256': 'frontend'}})
        analyzer = SimpleNamespace(check=lambda: None, cancel=release.set)
        with patch('music_studio.server.ModelBundle', return_value=bundle), patch('music_studio.server.Analyzer', return_value=analyzer):
            try:
                self.studio.analyze('powerful')
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.studio.state['busy'])
                self.start()
                self.assertEqual(self.finish()['status'], 'done')
                self.assertTrue(self.studio.state['busy'], 'Finishing stems cannot finish the chord worker.')
                self.assertIsNone(self.studio.state['result'])
            finally:
                release.set()
                self.studio.worker.join(3)
            self.assertFalse(self.studio.worker.is_alive())
            self.assertTrue(self.studio.state['result']['cached'])
            self.assertFalse(self.studio.state['busy'])

    def test_cancel_analysis_does_not_cancel_background_separation(self):
        self.start()
        cancelled = threading.Event()
        self.studio.analyzer = SimpleNamespace(cancel=cancelled.set)
        self.assertEqual(self.request('/api/cancel', {})[0], 200)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(self.jobs.cancel_event.is_set())
        self.assertEqual(self.finish()['status'], 'done')

    def test_worker_start_failure_cleans_up_and_allows_retry(self):
        with patch('music_studio.stem_jobs.threading.Thread.start', side_effect=RuntimeError('unavailable')):
            with self.assertRaises(ValueError):
                self.jobs.start()
        self.assertIsNone(self.jobs.worker)
        self.assertEqual(self.jobs.snapshot()['status'], 'failed')
        self.assertEqual(list(self.jobs.root.iterdir()), [])
        self.assertFalse(self.studio.state['busy'])
        self.start()
        self.assertEqual(self.finish()['status'], 'done')

    def test_background_job_allows_import_and_keeps_chord_state_independent(self):
        identity = self.start()
        self.assertFalse(self.studio.state['busy'])
        self.assertEqual(self.request('/api/stems-start', {})[0], 400)
        self.assertEqual(self.request('/api/import', raw=wav_bytes(),
                                      headers={'X-File-Name': 'other.wav'})[0], 200)
        other = self.studio.source
        # Simulate an independently running chord worker. Stem progress,
        # cancellation and completion must never clear its busy/status state.
        self.studio.state.update(busy=True, progress='Analysing chords…')
        self.assertEqual(self.request('/api/stems-cancel', {})[0], 200)
        self.assertTrue(self.jobs.cancel_event.is_set())
        self.assertTrue(self.studio.state['busy'])
        self.assertEqual(self.finish()['status'], 'cancelled')
        self.assertEqual(self.studio.source, other)
        self.assertTrue(self.studio.state['busy'])
        self.assertEqual(self.studio.state['progress'], 'Analysing chords…')
        self.studio.state['busy'] = False
        self.assertEqual(list(self.jobs.root.iterdir()), [])
        self.assertEqual(self.request('/api/stem-file?jobId=' + identity + '&stem=vocals')[0], 400)

    def test_failure_does_not_publish_partial_or_foreign_outputs(self):
        for mode in ('failure', 'outside', 'missing'):
            with self.subTest(mode=mode):
                self.separator = ControlledSeparator()
                self.separator.mode = mode
                self.jobs.separator_factory = self.separator
                identity = self.start()
                state = self.finish()
                self.assertEqual(state['status'], 'failed')
                self.assertEqual(state['stems'], [])
                self.assertFalse(self.studio.state['busy'])
                self.assertEqual(self.studio.source, self.source)
                self.assertTrue(self.source.exists())
                self.assertFalse((self.jobs.root / identity).exists())
                self.assertFalse((self.jobs.root / ('.' + identity)).exists())

    def test_exports_and_selection_reject_foreign_jobs_and_path_inputs(self):
        identity = self.start()
        self.finish()
        for job, stem in [('other', 'vocals'), (identity, '../My recording'),
                          (identity, '../../private'), (identity, 'VOCALS')]:
            with self.subTest(job=job, stem=stem):
                self.assertEqual(self.request('/api/stem-file?' + urlencode({'jobId': job, 'stem': stem}))[0], 400)
                self.assertEqual(self.request('/api/stems-select', {'jobId': job, 'stem': stem})[0], 400)
                self.assertEqual(self.studio.source, self.source)
        self.assertEqual(self.request('/api/stems-select', {'jobId': identity, 'stem': ['vocals']})[0], 400)

    def test_authentication_origin_and_mac_presentation_are_required(self):
        self.assertEqual(self.request('/api/stems', token=False)[0], 403)
        self.assertEqual(self.request('/api/stems-start', {}, token=False)[0], 403)
        self.assertEqual(self.request('/api/stems', headers={'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('/api/stems-start', {}, headers={'Origin': 'https://example.com'})[0], 403)
        self.studio.presentation = 'desktop'
        self.assertEqual(self.request('/api/stems')[0], 400)
        self.assertEqual(self.request('/api/stems-start', {})[0], 400)
        self.assertFalse(self.studio.state['busy'])

    def test_close_cancels_and_joins_worker_before_session_disposal(self):
        self.start()
        # A real cancellable worker leaves when cancellation becomes visible.
        releaser = threading.Thread(target=lambda: (self.jobs.cancel_event.wait(2),
                                                    self.separator.release.set()), daemon=True)
        releaser.start()
        self.jobs.close()
        releaser.join(3)
        self.assertFalse(self.jobs.worker.is_alive())
        self.assertEqual(self.jobs.snapshot()['status'], 'cancelled')
        self.assertEqual(list(self.jobs.root.iterdir()), [])
        self.assertTrue(self.source.exists())
        self.assertEqual(self.request('/api/stems-start', {})[0], 400)

    def test_upload_can_finish_while_separation_retains_its_original_recording(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        payload = wav_bytes()
        try:
            connection.putrequest('POST', '/api/import')
            connection.putheader('X-Blaze-Token', self.studio.token)
            connection.putheader('X-File-Name', 'Late upload.wav')
            connection.putheader('Content-Length', str(len(payload)))
            connection.endheaders()
            connection.send(payload[:32])
            deadline = time.monotonic() + 2
            while not list(self.studio.incoming.iterdir()) and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(list(self.studio.incoming.iterdir()), 'Upload did not reach its temporary file.')
            self.start()
            connection.send(payload[32:])
            response = connection.getresponse()
            self.assertEqual(response.status, 200, response.read())
            self.assertNotEqual(self.studio.source, self.source)
            self.assertEqual(self.studio.source_revision, 1)
            self.assertEqual(self.separator.source_bytes, wav_bytes())
            self.assertEqual(len(list(self.studio.incoming.iterdir())), 1)
            self.assertEqual(self.finish()['status'], 'done')
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
