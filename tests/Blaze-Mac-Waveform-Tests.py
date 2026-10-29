"""Real stereo envelopes, bounded decoding and authenticated session ownership."""
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio, create_server
from music_studio.stem_jobs import StemJobs
from music_studio.waveform import Waveforms, StaleWaveform


def recording(path, amplitude=.5):
    count, rate = 16000, 4000
    phase = np.arange(count, dtype='float64') / rate
    samples = np.stack((np.sin(phase * 2 * np.pi * 37) * amplitude,
                        np.sin(phase * 2 * np.pi * 83) * amplitude / 2), axis=1)
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(np.asarray(samples * 32767, dtype='<i2').tobytes())


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class WaveformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'recording.wav'
        recording(self.source)
        self.waveforms = Waveforms(shutil.which('ffmpeg'))

    def tearDown(self):
        self.waveforms.close()
        self.temp.cleanup()

    def test_real_stereo_has_distinct_channels_and_bounded_finite_peaks(self):
        value = self.waveforms.get(self.source)
        self.assertEqual(value['duration'], 4)
        self.assertEqual(value['decodeRate'], 4000)
        self.assertEqual(value['channels'], 2)
        self.assertEqual(value['sourceSampleRate'], 4000)
        self.assertEqual(value['sourceBits'], 16)
        self.assertEqual(value['sourceEncoding'], 'pcm')
        peaks = np.asarray(value['peaks'])
        self.assertEqual(peaks.shape, (2, 8192, 2))
        self.assertTrue(np.isfinite(peaks).all())
        self.assertTrue((peaks[:, :, 0] <= peaks[:, :, 1]).all())
        self.assertAlmostEqual(float(peaks[0].max()), .5, places=3)
        self.assertAlmostEqual(float(peaks[1].max()), .25, places=3)
        self.assertFalse(np.array_equal(peaks[0], peaks[1]))

    def test_replacing_source_invalidates_cached_samples(self):
        first = self.waveforms.get(self.source)
        replacement = self.root / 'replacement.wav'
        recording(replacement, .125)
        replacement.replace(self.source)
        second = self.waveforms.get(self.source)
        self.assertNotEqual(first['peaks'], second['peaks'])
        self.assertAlmostEqual(float(np.asarray(second['peaks']).max()), .125, places=3)

    def test_cache_does_not_bypass_session_change_or_shutdown(self):
        self.waveforms.get(self.source)
        with self.assertRaises(StaleWaveform):
            self.waveforms.get(self.source, lambda: False)
        checks = iter((True, False))
        with self.assertRaises(StaleWaveform):
            self.waveforms.get(self.source, lambda: next(checks))
        self.waveforms.close()
        with self.assertRaises(StaleWaveform):
            self.waveforms.get(self.source)

    def test_input_and_duration_limits_fail_cleanly(self):
        with patch('music_studio.waveform.MAX_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'smaller than 2 GB'):
                self.waveforms.get(self.source)
        with patch('music_studio.waveform.MAX_SECONDS', .1):
            with self.assertRaisesRegex(ValueError, 'two hours'):
                self.waveforms.get(self.source)
        bad = self.root / 'unreadable.wav'
        bad.write_bytes(b'not audio')
        with self.assertRaisesRegex(ValueError, 'readable audio'):
            self.waveforms.get(bad)

    @unittest.skipIf(os.name == 'nt', 'Executable shim requires a POSIX host')
    def test_changed_session_terminates_and_reaps_decoder(self):
        executable = self.root / 'slow-ffmpeg'
        pid_file = self.root / 'decoder-pid'
        executable.write_text('#!' + sys.executable + '\nimport os,sys\n'
                              + 'open(' + repr(str(pid_file)) + ',"w").write(str(os.getpid()))\n'
                              + 'os.execv(' + repr(shutil.which('ffmpeg')) + ',['
                              + repr(shutil.which('ffmpeg')) + ',"-re",*sys.argv[1:]])\n')
        executable.chmod(0o755)
        self.waveforms.ffmpeg = str(executable)
        changed = threading.Event()
        timer = threading.Timer(.2, changed.set)
        timer.start()
        try:
            with self.assertRaises(StaleWaveform):
                self.waveforms.get(self.source, lambda: not changed.is_set())
        finally:
            timer.cancel()
            timer.join()
        self.assertTrue(pid_file.is_file())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class WaveformHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'recording.wav'
        recording(self.source)
        self.studio = Studio(self.root / 'data', shutil.which('ffmpeg'), self.source)
        self.studio.presentation = 'mac'
        self.jobs = self.studio.stems = StemJobs(self.studio)
        self.jobs.root.mkdir(parents=True)
        self.jobs.files = {}
        for stem in ('vocals', 'piano', 'synths'):
            target = self.jobs.root / (stem + '.wav')
            recording(target, {'vocals': .5, 'piano': .25, 'synths': .125}[stem])
            self.jobs.files[stem] = target
        self.jobs.value.update(status='done', jobId='completed-local-job', sourceRevision=0,
                               stems=[{'id': stem} for stem in self.jobs.files])
        self.server = create_server(self.studio)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.studio.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.temp.cleanup()

    def get(self, query, headers=None, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        outgoing = {'X-Blaze-Token': self.studio.token} if token else {}
        outgoing.update(headers or {})
        try:
            connection.request('GET', '/api/studio-waveform?' + query, headers=outgoing)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_authorization_origin_and_mac_only_boundary(self):
        self.assertEqual(self.get('sourceRevision=0', token=False)[0], 403)
        self.assertEqual(self.get('sourceRevision=0', {'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.get('sourceRevision=0', {'Host': 'example.com'})[0], 403)
        self.studio.presentation = 'desktop'
        self.assertEqual(self.get('sourceRevision=0')[0], 404)

    def test_current_source_and_stem_use_real_distinct_audio(self):
        status, source = self.get('sourceRevision=0')
        self.assertEqual(status, 200)
        self.assertEqual(source['stemJobId'], 'completed-local-job')
        self.assertEqual(source['selectedStem'], '')
        query = urlencode(dict(sourceRevision=0, jobId='completed-local-job', stem='synths'))
        status, stem = self.get(query)
        self.assertEqual(status, 200)
        self.assertEqual(stem['sourceRevision'], 0)
        self.assertEqual(stem['stem'], 'synths')
        self.assertEqual(stem['selectedStem'], '', 'Previewing a sibling must not select it.')
        self.assertNotEqual(source['peaks'], stem['peaks'])
        self.assertNotIn(str(self.root), json.dumps(stem))

    def test_cancelled_fetch_does_not_write_a_second_error_response(self):
        prepared, release, responded, crashed = (threading.Event() for _ in range(4))
        original_decode = Waveforms._decode
        handler = self.server.RequestHandlerClass
        original_json = handler.json

        def delayed_decode(instance, source, valid):
            value = original_decode(instance, source, valid)
            prepared.set()
            if not release.wait(3):
                raise ValueError('The test did not release its prepared waveform.')
            return value

        def observe_response(instance, *args, **kwargs):
            try:
                return original_json(instance, *args, **kwargs)
            finally:
                responded.set()

        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        with patch.object(Waveforms, '_decode', delayed_decode), \
                patch.object(handler, 'json', observe_response), \
                patch.object(self.server, 'handle_error', side_effect=lambda *_: crashed.set()):
            try:
                connection.request('GET', '/api/studio-waveform?sourceRevision=0',
                                   headers={'X-Blaze-Token': self.studio.token})
                self.assertTrue(prepared.wait(3))
                connection.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                connection.close()
                release.set()
                self.assertTrue(responded.wait(3))
                self.assertFalse(crashed.wait(.05), 'A cancelled fetch escaped the response handler.')
                self.assertEqual(self.get('sourceRevision=0')[0], 200)
            finally:
                release.set()
                connection.close()

    def test_selected_stem_retains_siblings_but_new_import_invalidates_job(self):
        self.jobs.select('completed-local-job', 'piano')
        status, selected = self.get('sourceRevision=1')
        self.assertEqual(status, 200)
        self.assertEqual(selected['stemJobId'], 'completed-local-job')
        self.assertEqual(selected['selectedStem'], 'piano')
        sibling = urlencode(dict(sourceRevision=1, jobId='completed-local-job', stem='synths'))
        status, preview = self.get(sibling)
        self.assertEqual(status, 200)
        self.assertEqual(preview['stem'], 'synths')
        self.assertEqual(preview['selectedStem'], 'piano')
        unrelated = self.root / 'new-recording.wav'
        recording(unrelated, .4)
        self.studio.open_local_file(unrelated)
        self.assertEqual(self.get(sibling)[0], 409)
        orphan = urlencode(dict(sourceRevision=2, jobId='completed-local-job', stem='synths'))
        self.assertEqual(self.get(orphan)[0], 400)
        self.assertEqual(self.get('sourceRevision=2')[1]['stemJobId'], '')
        self.assertEqual(self.get('sourceRevision=2')[1]['selectedStem'], '')

    def test_recording_named_like_a_stem_is_not_the_saved_output(self):
        for name, stem in (('Piano.wav', 'piano'), ('Vocals.wav', 'vocals')):
            with self.subTest(name=name):
                original = self.root / name
                recording(original, .35)
                self.studio.open_local_file(original)
                # A completed separation belongs to this original source.
                self.jobs.value['sourceRevision'] = self.studio.source_revision
                status, mix = self.get('sourceRevision=' + str(self.studio.source_revision))
                self.assertEqual(status, 200)
                self.assertEqual(mix['stemJobId'], 'completed-local-job')
                self.assertEqual(mix['selectedStem'], '')
                self.assertNotIn(str(self.root), json.dumps(mix))
                self.jobs.select('completed-local-job', stem)
                self.assertEqual(self.studio.name, name, 'The display names intentionally collide.')
                status, output = self.get('sourceRevision=' + str(self.studio.source_revision))
                self.assertEqual(status, 200)
                self.assertEqual(output['selectedStem'], stem)
                self.assertNotEqual(output['peaks'], mix['peaks'])
                self.assertNotIn(str(self.root), json.dumps(output))

    def test_selected_identity_uses_canonical_path_and_current_completed_outputs(self):
        self.jobs.select('completed-local-job', 'piano')
        normalization = self.jobs.root / 'normalization'
        normalization.mkdir()
        self.jobs.files['piano'] = normalization / '..' / 'piano.wav'
        self.studio.open_local_file(self.jobs.root / 'piano.wav')
        status, canonical = self.get('sourceRevision=' + str(self.studio.source_revision))
        self.assertEqual(status, 200)
        self.assertEqual(canonical['stemJobId'], 'completed-local-job')
        self.assertEqual(canonical['selectedStem'], 'piano')

        self.jobs.value['status'] = 'running'
        status, pending = self.get('sourceRevision=' + str(self.studio.source_revision))
        self.assertEqual(status, 200)
        self.assertEqual(pending['stemJobId'], '')
        self.assertEqual(pending['selectedStem'], '')

        # Separating the selected output again creates a new job. The old piano
        # file is this job's recording, not its new piano output of the same name.
        fresh = self.jobs.root / 'fresh'
        fresh.mkdir()
        recording(fresh / 'piano.wav', .7)
        self.jobs.files = {'piano': fresh / 'piano.wav'}
        self.jobs.value.update(status='done', jobId='fresh-job',
                               sourceRevision=self.studio.source_revision,
                               stems=[{'id': 'piano'}])
        status, original = self.get('sourceRevision=' + str(self.studio.source_revision))
        self.assertEqual(status, 200)
        self.assertEqual(original['stemJobId'], 'fresh-job')
        self.assertEqual(original['selectedStem'], '')
        self.jobs.select('fresh-job', 'piano')
        status, output = self.get('sourceRevision=' + str(self.studio.source_revision))
        self.assertEqual(status, 200)
        self.assertEqual(output['selectedStem'], 'piano')
        self.assertNotEqual(output['peaks'], original['peaks'])

    def test_rejects_missing_stale_duplicate_and_forged_track_references(self):
        for query in ('', 'sourceRevision=1', 'sourceRevision=-1', 'sourceRevision=not-a-number'):
            self.assertEqual(self.get(query)[0], 409)
        for query in ('sourceRevision=0&sourceRevision=0',
                      'sourceRevision=0&jobId=not-current&stem=piano',
                      'sourceRevision=0&jobId=completed-local-job&stem=../../recording',
                      'sourceRevision=0&stem=piano'):
            self.assertEqual(self.get(query)[0], 400)


if __name__ == '__main__':
    unittest.main()
