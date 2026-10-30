"""Stem job lifecycle and authenticated HTTP/file ownership contracts.

The separator is controlled here; real SCNet inference is checked separately.
"""
import http.client
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
            self.assertEqual(headers['Content-Disposition'], 'attachment; filename="' + stem.title() + '.wav"')
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
