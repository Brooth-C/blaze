"""Real WAV export, independent tempo/pitch, ZIP contents and request bounds."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
import wave
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.server import Studio
from music_studio.stem_jobs import StemJobs
from music_studio.practice_audio import PracticeAudio


class PracticeAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'Tone.wav'
        samples = (np.sin(np.arange(44100 * 2) / 44100 * 2 * np.pi * 440) * 12000).astype('<i2')
        with wave.open(str(self.source), 'wb') as audio:
            audio.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
            audio.writeframes(samples.tobytes())
        decoder = shutil.which('ffmpeg')
        if not decoder:
            self.skipTest('ffmpeg required for real pitch verification')
        self.studio = Studio(self.root / 'data', decoder, self.source)
        self.studio.presentation = 'mac'
        self.addCleanup(self.studio.close)
        self.audio = PracticeAudio(self.studio)
        self.studio.practice_audio = self.audio

    def render(self, **values):
        answer = self.audio.request(dict(sourceRevision=self.studio.source_revision, **values))
        deadline = time.monotonic() + 15
        while answer['status'] == 'pending' and time.monotonic() < deadline:
            time.sleep(.02)
            answer = self.audio.status(answer['requestId'])
        self.assertEqual(answer['status'], 'ready', answer)
        return answer, self.audio.file(answer['requestId'])[0]

    def test_transpose_changes_frequency_without_changing_tempo(self):
        import subprocess
        answer, target = self.render(kind='source', semitones=2)
        raw = subprocess.run([self.studio.ffmpeg, '-v', 'error', '-i', str(target), '-f', 'f32le', '-'],
                             check=True, capture_output=True).stdout
        samples = np.frombuffer(raw, dtype='<f4')
        peak = np.fft.rfftfreq(len(samples), 1 / 44100)[np.argmax(np.abs(np.fft.rfft(samples)))]
        self.assertAlmostEqual(peak, 440 * 2 ** (2 / 12), delta=2)
        self.assertAlmostEqual(len(samples) / 44100, 2, delta=.08)
        self.assertIn('+2', answer['filename'])
        self.assertEqual(self.studio.source, self.source)
        self.assertEqual(self.studio.source_revision, 0)
        self.assertEqual(self.audio.request({'sourceRevision': 0, 'kind': 'source', 'semitones': 2})['requestId'], answer['requestId'])

    def test_both_download_contains_two_separate_original_wavs(self):
        source = self.source

        class ControlledSeparator:
            def __init__(self, *_):
                pass

            def separate(self, _source, output_dir, **_):
                result = {}
                for name in ('piano', 'accompaniment'):
                    target = output_dir / (name + '.wav')
                    shutil.copyfile(source, target)
                    result[name] = target
                return result

        self.studio.stems = StemJobs(self.studio, separator_factory=ControlledSeparator)
        job = self.studio.stems.start('piano')['jobId']
        self.studio.stems.worker.join(5)
        _, target = self.render(kind='both', semitones=0, jobId=job)
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(set(archive.namelist()), {'Piano.wav', 'Backing.wav'})
            self.assertEqual(archive.read('Piano.wav'), source.read_bytes())
            self.assertEqual(archive.read('Backing.wav'), source.read_bytes())

    def test_rejects_stale_invalid_and_unregistered_audio(self):
        for body in ({'sourceRevision': 1}, {'sourceRevision': True}, {'sourceRevision': 0, 'semitones': 13},
                     {'sourceRevision': 0, 'semitones': True}, {'sourceRevision': 0, 'kind': '../private'},
                     {'sourceRevision': 0, 'kind': 'both'}):
            with self.subTest(body=json.dumps(body)), self.assertRaises(ValueError):
                self.audio.request(body)
        with self.assertRaises(ValueError):
            self.audio.file('../../private')

    def test_active_playback_survives_export_and_request_eviction(self):
        active, target = self.render(kind='source', semitones=1)
        identity = active['requestId']
        expected = target.read_bytes()
        self.audio.file(identity, playback=True)
        # More than both retention bounds; exports must not disown the player.
        for semitones in [n for n in range(-8, 10) if n != 1]:
            self.render(kind='source', semitones=semitones)
            self.assertEqual(self.audio.file(identity)[0].read_bytes(), expected)
            self.assertLessEqual(len(list(self.audio.root.iterdir())), 4)
            self.assertLessEqual(len(self.audio.jobs), 16)
        self.assertEqual(self.audio.status(identity)['status'], 'ready')
        replacement, _ = self.render(kind='source', semitones=10)
        self.audio.file(replacement['requestId'], playback=True)
        for semitones in (11, 12, -12, -11):
            self.render(kind='source', semitones=semitones)
        self.assertFalse(target.exists(), 'Released playback should become evictable')


if __name__ == '__main__':
    unittest.main()
