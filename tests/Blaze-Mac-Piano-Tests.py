"""Piano transform, cancellation and real pinned-model integration checks."""
from pathlib import Path
import os
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from music_studio.piano import PianoSeparator, analyse, synthesise, piano_mask, SEGMENT
from music_studio.stems import SeparationCancelled


class PianoTests(unittest.TestCase):
    def test_joint_mask(self):
        x = np.ones((1, 2, 512, 1024), dtype=np.float32)
        equal = piano_mask([np.zeros_like(x[0]) for _ in range(5)], x)
        np.testing.assert_allclose(equal, .2, atol=1e-6)
        strong = [np.full_like(x[0], -5) for _ in range(5)]
        strong[2][:] = 5
        self.assertGreater(float(piano_mask(strong, x).min()), .999)

    def test_transform_alignment(self):
        # In-band sinusoid with zero-padded edges retains timing and amplitude.
        t = np.arange(SEGMENT)
        audio = np.stack((np.sin(2*np.pi*220*t/44100), np.sin(2*np.pi*330*t/44100))).astype('float32')
        spectrum, magnitude = analyse(audio)
        self.assertEqual(magnitude.shape, (1, 2, 512, 1024))
        output = synthesise(spectrum, np.ones((2,512,1024),dtype='float32'), SEGMENT)
        self.assertLess(float(np.sqrt(np.mean((output[:,4096:-4096]-audio[:,4096:-4096])**2))), 1e-5)

    def test_cancel_before_loading(self):
        event = threading.Event(); event.set()
        with self.assertRaises(SeparationCancelled):
            PianoSeparator().separate('missing.wav', 'unused', cancel_event=event)

    def test_bad_model(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'missing'):
                PianoSeparator(d)._graph('piano', np.zeros((1,2,512,1024),dtype='float32'), threading.Event())

    def test_length_reconstruction_and_cleanup(self):
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg is required')
        class Controlled(PianoSeparator):
            def _graph(self, name, features, event):
                return np.zeros_like(features[0])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'mix.wav'
            samples=(np.random.default_rng(1).normal(0,1000,(SEGMENT+137,2))).astype('<i2')
            with wave.open(str(source),'wb') as out:
                out.setparams((2,2,44100,0,'NONE','not compressed')); out.writeframes(samples.tobytes())
            tracks=Controlled().separate(source,root/'out')
            decoded=[]
            for path in tracks.values():
                raw=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','f32le','-'],check=True,capture_output=True).stdout
                decoded.append(np.frombuffer(raw,dtype='<f4').reshape(-1,2))
            self.assertEqual(decoded[0].shape,samples.shape)
            np.testing.assert_allclose(sum(decoded),samples.astype('float32')/32768,atol=1e-7)
            self.assertEqual(set(tracks),{'piano','accompaniment'})

    @unittest.skipUnless(os.environ.get('BLAZE_STEM_MODEL_DIR'), 'Real model requested after staging')
    def test_original_checkpoint_reference(self):
        reference=json.loads((Path(__file__).parent/'media/piano-reference.json').read_text())
        x=np.random.default_rng(reference['seed']).uniform(0,2,(1,2,512,1024)).astype('float32')
        separator=PianoSeparator(os.environ['BLAZE_STEM_MODEL_DIR'])
        logits=[separator._graph(name,x,threading.Event()) for name in ('drums','bass','piano','other','vocals')]
        actual=piano_mask(logits,x).ravel()[reference['indices']]
        np.testing.assert_allclose(actual,reference['piano_mask'],atol=.002,rtol=.01)

    @unittest.skipUnless(os.environ.get('BLAZE_STEM_MODEL_DIR'), 'Real model requested after staging')
    def test_real_piano(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'mix.wav'
            t=np.arange(44100)/44100
            audio=np.stack((np.sin(2*np.pi*220*t)*.1,np.sin(2*np.pi*330*t)*.1),axis=1)
            with wave.open(str(source),'wb') as out:
                out.setparams((2,2,44100,0,'NONE','not compressed'));out.writeframes((audio*32767).astype('<i2').tobytes())
            progress=[]
            result=PianoSeparator(os.environ['BLAZE_STEM_MODEL_DIR']).separate(source,root/'out',progress=lambda x,m:progress.append(x))
            self.assertTrue(all(0<=x<=1 for x in progress))
            for path in result.values():
                self.assertEqual(path.stat().st_size,58+44100*8)
                data=np.frombuffer(path.read_bytes()[58:],dtype='<f4')
                self.assertTrue(np.isfinite(data).all())
            self.assertGreater(float(np.max(np.abs(np.frombuffer(result['piano'].read_bytes()[58:],dtype='<f4')))),0)


if __name__=='__main__':unittest.main()
