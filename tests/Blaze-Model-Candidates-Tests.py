"""Candidate opt-in, archive integrity, signature and full reference parity."""
from pathlib import Path
import importlib.util
import os
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from music_studio.chordmini import ChordMiniBundle, ChordMiniAnalyzer
from music_studio.native_scnet import NativeSCNetSeparator, verified_package, INPUT_SHAPE, OUTPUT_SHAPE
from music_studio.stems import SeparationCancelled


class CandidateTests(unittest.TestCase):
    def test_chord_windows_normalize_padding_before_logit_voting(self):
        bundle = ChordMiniBundle.__new__(ChordMiniBundle)
        bundle.contract = {'mean':-2.,'std':3.}
        inputs = []
        def predict(_,values):
            x = values['features'];inputs.append(x.copy())
            out = np.zeros((1,108,170),dtype='float32')
            out[:,:,2] = x[:,:,0]
            return [out]
        bundle.network = Mock(run=predict)
        features = np.ones((109,144),dtype='float32')
        labels = bundle.predict_features(features)
        self.assertEqual(len(inputs),3)
        np.testing.assert_array_equal(inputs[-1][0,1:],np.full((107,144),2/3,dtype='float32'))
        self.assertEqual(labels.shape,(109,))
        self.assertTrue(np.all(labels==2))

    def test_chord_cancellation_stops_before_inference(self):
        bundle = ChordMiniBundle.__new__(ChordMiniBundle)
        bundle.network = Mock()
        def cancel():raise SeparationCancelled('cancelled')
        with self.assertRaises(SeparationCancelled):
            bundle.predict_features(np.zeros((108,144)),check=cancel)
        bundle.network.assert_not_called()

    def test_native_checks_cancel_before_loading_or_prediction(self):
        engine = NativeSCNetSeparator('/not-installed')
        event = threading.Event();event.set()
        with self.assertRaises(SeparationCancelled):engine._load(event)
        with self.assertRaises(SeparationCancelled):engine._predict(None,event)
        self.assertIsNone(engine.session)

    def test_native_gpu_load_validates_signature_and_releases(self):
        engine = NativeSCNetSeparator('/fixture')
        model = Mock()
        feature = lambda shape:SimpleNamespace(name='x',type=SimpleNamespace(multiArrayType=SimpleNamespace(shape=shape,dataType=65552)))
        model.get_spec.return_value = SimpleNamespace(description=SimpleNamespace(input=[feature(INPUT_SHAPE)],output=[feature(OUTPUT_SHAPE)]))
        ct = SimpleNamespace(models=SimpleNamespace(MLModel=Mock(return_value=model)),ComputeUnit=SimpleNamespace(CPU_AND_GPU='gpu'))
        with patch.dict(sys.modules,{'coremltools':ct}),patch('music_studio.native_scnet.sys.platform','darwin'),patch('music_studio.native_scnet.platform.machine',return_value='arm64'),patch('music_studio.native_scnet.verified_package',return_value=(Path('/fixture'),{'archive_sha256':'pinned'})):
            engine._load(threading.Event())
        ct.models.MLModel.assert_called_once_with('/fixture',compute_units='gpu')
        session = engine.session
        engine.runtime.finish(session)
        self.assertIsNone(session.model)

    def test_native_prediction_converts_precision_and_rejects_overflow(self):
        engine = NativeSCNetSeparator('/fixture')
        engine.input_name,engine.output_name,engine.input_dtype = 'in','out',np.float16
        model = Mock()
        model.predict.return_value = {'out':np.broadcast_to(np.float16(.5),OUTPUT_SHAPE)}
        engine.session = SimpleNamespace(model=model)
        features = np.zeros(INPUT_SHAPE,dtype=np.float32)
        result = engine._predict(features,threading.Event())
        self.assertEqual(result.dtype,np.float32)
        self.assertEqual(model.predict.call_args.args[0]['in'].dtype,np.float16)
        model.predict.reset_mock()
        features.flat[0] = 1e6
        with self.assertRaisesRegex(ValueError,'precision range'):
            engine._predict(features,threading.Event())
        model.predict.assert_not_called()

    def test_native_cancellation_after_prediction_discards_output(self):
        engine = NativeSCNetSeparator('/fixture')
        engine.input_name,engine.output_name,engine.input_dtype = 'in','out',np.float16
        event = threading.Event()
        def predict(_):
            event.set()
            return {'out':np.broadcast_to(np.float16(0),OUTPUT_SHAPE)}
        engine.session = SimpleNamespace(model=Mock(predict=predict))
        with self.assertRaises(SeparationCancelled):
            engine._predict(np.zeros(INPUT_SHAPE,dtype=np.float32),event)

    @unittest.skipUnless(os.environ.get('BLAZE_TEST_NATIVE_SCNET_DIR'),'Staged real native package needed')
    def test_real_native_package_integrity_detects_corruption(self):
        root = Path(os.environ['BLAZE_TEST_NATIVE_SCNET_DIR'])
        package,manifest = verified_package(root)
        self.assertTrue(package.is_dir());self.assertEqual(len(manifest['files']),3)
        with tempfile.TemporaryDirectory() as folder:
            import shutil
            target = Path(folder)/'candidate'
            shutil.copytree(root,target)
            path = target/next(iter(manifest['files']))
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):verified_package(target)

    @unittest.skipUnless(os.environ.get('BLAZE_TEST_CHORDMINI_DIR') and importlib.util.find_spec('librosa'),'Real model/reference environment needed')
    def test_real_chordmini_matches_upstream_logits_and_full_audio_pipeline(self):
        import librosa
        import torch
        import wave
        from music_studio.store import validate
        source = Path(os.environ['BLAZE_TEST_CHORDMINI_SOURCE'])
        sys.path.insert(0,str(source))
        from src.models.btc_model import BTC_model
        # Load reference helpers without the unrelated plotting package initializer.
        for name, filename in [('src.evaluation.utils.common','common.py'),('chordmini_reference','inference.py')]:
            spec = importlib.util.spec_from_file_location(name,source/'src/evaluation/utils'/filename)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        predict_sliding_windows = module.predict_sliding_windows
        import yaml
        saved = torch.load(source/'checkpoints/btc_model_best.pth',map_location='cpu',weights_only=True)
        model = BTC_model(yaml.safe_load((source/'config/ChordMini.yaml').read_text())['model']).eval()
        model.load_state_dict(saved['model_state_dict'],strict=True)
        torch.set_num_threads(2)
        for length in (1,107,108,109,217):
            features = np.random.default_rng(length).normal(-2,1,(length,144)).astype('float32')
            bundle = ChordMiniBundle(os.environ['BLAZE_TEST_CHORDMINI_DIR'])
            expected = predict_sliding_windows(model,features,float(saved['normalization']['mean']),float(saved['normalization']['std']),108,1,'BTC',170,vote_aggregation='logit',use_overlap=True,overlap_ratio=.5)
            actual = bundle.predict_features(features)
            np.testing.assert_array_equal(actual,expected)
            bundle.close()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'fixture.wav'
            audio = (.1*np.sin(2*np.pi*220*np.arange(12*22050)/22050)).astype('float32')
            with wave.open(str(path),'wb') as stream:
                stream.setparams((1,2,22050,0,'NONE','not compressed'))
                stream.writeframes((audio*32767).astype('<i2').tobytes())
            bundle = ChordMiniBundle(os.environ['BLAZE_TEST_CHORDMINI_DIR'])
            result = ChordMiniAnalyzer(bundle,'ffmpeg').analyze(path)
            validate(result)
            self.assertEqual(result['duration'],12.)
            self.assertTrue(result['chords'])
            pcm,_ = librosa.load(path,sr=22050)
            features = np.log(np.abs(librosa.cqt(pcm,sr=22050,n_bins=144,bins_per_octave=24,hop_length=2048,fmin=librosa.note_to_hz('C1')))+1e-6).T.astype('float32')
            expected = predict_sliding_windows(model,features,float(saved['normalization']['mean']),float(saved['normalization']['std']),108,1,'BTC',170,vote_aggregation='logit',use_overlap=True,overlap_ratio=.5)
            for event in result['chords']:
                index = round(event['start']*22050/2048)
                self.assertEqual(event['chord'],bundle.metadata['labels'][int(expected[index])])
            from music_studio.server import Studio
            studio = Studio(Path(folder)/'studio','ffmpeg',path)
            studio.presentation = 'mac'
            with patch.dict(os.environ,{'BLAZE_EXPERIMENTAL_CHORDMINI_DIR':os.environ['BLAZE_TEST_CHORDMINI_DIR']}):
                try:
                    studio.analyze('powerful');studio.worker.join(60)
                    self.assertFalse(studio.state['busy'])
                    self.assertIsNone(studio.state['error'])
                    self.assertEqual(studio.state['result']['engine_version'],result['engine_version'])
                    with patch('music_studio.chordmini.ChordMiniAnalyzer',side_effect=AssertionError('Cache must skip inference')):
                        studio.analyze('powerful');studio.worker.join(10)
                    self.assertIsNone(studio.state['error'])
                finally:studio.close()



if __name__ == '__main__':unittest.main()
