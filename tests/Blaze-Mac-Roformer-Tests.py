"""RoFormer transform, long-recording streaming and five-output ownership."""
from pathlib import Path
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.roformer import RoformerSeparator, QualityFiveStemSeparator, SEGMENT
from music_studio.roformer_transform import stft_bands_last, istft_bands_last, overlap_envelope, stft
from music_studio.stems import SeparationCancelled


def recording(path, count):
    values = np.random.default_rng(37).integers(-4000, 4000, (count, 2), dtype='<i2')
    with wave.open(str(path), 'wb') as output:
        output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
        output.writeframes(values.tobytes())
    return values.astype('float32') / 32768


def samples(path):
    raw = path.read_bytes()
    return np.frombuffer(raw[58:], dtype='<f4').reshape(-1, 2)


class Controlled(RoformerSeparator):
    def _load(self, event):
        pass

    def _chunk(self, audio, event):
        return np.stack([audio * fraction for fraction in (.1, .2, .3, .4)])


class RoformerTests(unittest.TestCase):
    def test_batched_inverse_preserves_original_overlap_order_and_padding(self):
        from music_studio.roformer_transform import istft, hann_periodic
        rng=np.random.default_rng(188)
        for fft,hop,count in ((2048,512,255),(2048,512,256),(2048,512,257),(2048,512,1723),(2048,441,1101)):
            backing=(rng.normal(size=(fft//2+1,count*2))+1j*rng.normal(size=(fft//2+1,count*2))).astype(np.complex64)
            spec=backing[:,::2];spec.setflags(write=False)
            window=hann_periodic(fft)
            frames=np.fft.irfft(spec,n=fft,axis=0)*window[:,None]
            signal=np.zeros(fft+hop*(count-1))
            for i in range(count):signal[i*hop:i*hop+fft]+=frames[:,i]
            envelope=overlap_envelope(fft,hop,count)
            for length in (hop*(count-1),len(signal)+11):
                start=fft//2;stop=min(start+length,len(signal))
                expected=signal[start:stop]/envelope[start:stop]
                if len(expected)<length:expected=np.pad(expected,(0,length-len(expected)))
                self.assertEqual(istft(spec,fft,hop,length).tobytes(),expected.tobytes())

    def test_blocked_spectral_packing_preserves_chunk_boundaries_and_stereo_values(self):
        rng = np.random.default_rng(185)
        for length, hop in ((255*512,512),(256*512,512),(257*512,512),(882000,512),(485100,441)):
            audio = rng.normal(size=(2,length)).astype(np.float32)
            audio.setflags(write=False)
            spectrum = stft(audio,2048,hop)
            expected = np.stack((spectrum.real,spectrum.imag),axis=-1).transpose(1,0,2,3)
            expected = np.ascontiguousarray(expected.reshape(1,2050,spectrum.shape[-1],2),dtype=np.float32)
            actual = stft_bands_last(audio,2048,hop)
            self.assertEqual(actual.tobytes(),expected.tobytes())

    def test_borrowed_source_chunks_match_reflection_at_every_stream_boundary(self):
        from music_studio.roformer import source_chunk
        rng=np.random.default_rng(180)
        for segment in (485100,882000):
            for count in (137,segment+137,segment*2+137):
                pcm=rng.normal(0,.1,(count,2)).astype(np.float32)
                pcm.setflags(write=False)
                stride=segment//2;border=stride if count>2*stride else 0
                total=count+2*border
                for offset in range(0,min(total,border+count),stride):
                    length=min(segment,total-offset)
                    indices=np.arange(offset,offset+length)-border
                    indices=np.where(indices<0,-indices,indices)
                    indices=np.where(indices>=count,2*count-2-indices,indices)
                    expected=np.asarray(pcm[indices].T,dtype=np.float32)
                    actual=source_chunk(pcm,offset,length,border,count)
                    self.assertEqual(actual.tobytes(),expected.tobytes())
                    if 0<=offset-border and offset-border+length<=count:
                        self.assertTrue(np.shares_memory(actual,pcm))
                        self.assertFalse(actual.flags.writeable)
        pcm=np.arange(128,dtype=np.float64).reshape(64,2)
        self.assertEqual(source_chunk(pcm,4,31,0,64).tobytes(),pcm[4:35].T.astype(np.float32).tobytes())

    def test_reflection_slices_match_index_folding_on_small_and_extreme_edges(self):
        from music_studio.roformer import source_chunk
        for count in range(2,18):
            pcm=np.arange(count*2,dtype=np.float32).reshape(count,2)
            for first in (1-count,-1,0,count-2,count-1):
                for last in (first+1,0,1,count,2*count-2,2*count-1):
                    if last<=first:continue
                    border=count//2;offset=first+border;length=last-first
                    indices=np.arange(offset,offset+length)-border
                    indices=np.where(indices<0,-indices,indices)
                    indices=np.where(indices>=count,2*count-2-indices,indices)
                    expected=np.asarray(pcm[indices].T,dtype=np.float32)
                    actual=source_chunk(pcm,offset,length,border,count)
                    self.assertEqual(actual.tobytes(),expected.tobytes())

    def test_missing_model_and_tampered_block_fail_before_inference(self):
        from music_studio.roformer_assets import MODELS
        with tempfile.TemporaryDirectory() as d:
            engine = RoformerSeparator(d)
            with self.assertRaisesRegex(ValueError, 'missing or damaged'):
                engine._load(threading.Event())
            engine.directory.mkdir()
            meta = MODELS['front']
            (engine.directory / meta['file']).write_bytes(b'changed model')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                engine._graph(meta, np.zeros((1,), dtype='float32'), threading.Event())
            self.assertIsNone(engine.session)

    def test_stereo_spectral_transform_matches_original_layout(self):
        audio = np.random.default_rng(9).normal(0, .1, (2, 44100)).astype('float32')
        audio[0, 0], audio[1, -1] = 1.4, -1.2
        spec = stft_bands_last(audio, 2048, 441)
        restored = istft_bands_last(spec[0], 2, 2048, 441, audio.shape[-1])
        np.testing.assert_allclose(restored, audio, atol=1e-7)

    def test_direct_spectral_packing_matches_original_values_and_channel_order(self):
        rng = np.random.default_rng(52)
        for channels, length, fft, hop in ((2, 882000, 2048, 512), (2, 44100, 2048, 441), (1, 4096, 1024, 256)):
            audio = rng.normal(size=(channels, length)).astype(np.float32)
            spectrum = stft(audio, fft, hop)
            self.assertTrue(spectrum.flags.c_contiguous)
            original = np.stack([spectrum.real, spectrum.imag], axis=-1).transpose(1, 0, 2, 3)
            original = np.ascontiguousarray(original.reshape(-1, spectrum.shape[2], 2)[None].astype(np.float32))
            packed = stft_bands_last(audio, fft, hop)
            np.testing.assert_array_equal(packed, original)
            self.assertTrue(packed.flags.c_contiguous)
            self.assertEqual(packed.dtype, np.float32)

    def test_cached_window_envelope_matches_independent_overlap_for_distinct_shapes(self):
        for fft, hop, frames in ((2048,441,31), (2048,512,31), (1024,256,19)):
            window = .5*(1-np.cos(2*np.pi*np.arange(fft)/fft))
            expected = np.zeros(fft+hop*(frames-1))
            for i in range(frames):expected[i*hop:i*hop+fft] += window**2
            envelope = overlap_envelope(fft,hop,frames)
            np.testing.assert_array_equal(envelope,expected)
            self.assertIs(envelope,overlap_envelope(fft,hop,frames))
            self.assertFalse(envelope.flags.writeable)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_short_and_long_streaming_preserve_duration_alignment_and_mix(self):
        # Exercise zero-padded short clips and reflected borders for recordings
        # longer than a full context; deliberately cross all chunk boundaries.
        for count in (137, SEGMENT + 137, SEGMENT * 2 + 137):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as d:
                root = Path(d); source = root / 'mix.wav'
                original = recording(source, count)
                source_bytes = source.read_bytes()
                result = Controlled().separate(source, root / 'out')
                decoded = {name: samples(path) for name, path in result.items()}
                for name, fraction in zip(('drums', 'bass', 'other', 'vocals'), (.1, .2, .3, .4)):
                    self.assertEqual(decoded[name].shape, original.shape)
                    np.testing.assert_allclose(decoded[name], original * fraction, atol=1e-7)
                np.testing.assert_allclose(sum(decoded.values()), original, atol=1e-7)
                self.assertEqual(source.read_bytes(), source_bytes)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_overlap_add_keeps_shared_readonly_and_float64_predictions_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.wav';recording(source,137)
            expected=Controlled().separate(source,root/'baseline')
            for kind in ('shared','readonly','float64'):
                class Borrowed(Controlled):
                    def _chunk(self,audio,event):
                        values=super()._chunk(audio,event)
                        if kind=='shared':values=values.view()
                        elif kind=='readonly':values.setflags(write=False)
                        else:values=values.astype(np.float64)
                        self.borrowed=values;self.before=values.tobytes()
                        return values
                engine=Borrowed();actual=engine.separate(source,root/kind)
                self.assertEqual(engine.borrowed.tobytes(),engine.before)
                for stem in expected:
                    self.assertEqual(actual[stem].read_bytes(),expected[stem].read_bytes())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_padding_only_tail_does_not_run_an_extra_model_pass(self):
        calls = []
        class Counting(Controlled):
            def _chunk(self, audio, event):
                calls.append(1)
                return super()._chunk(audio, event)
        count = SEGMENT + 137
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.wav'
            original = recording(source, count)
            result = Counting().separate(source, root / 'out')
            stride = SEGMENT // 2
            self.assertEqual(len(calls), len(range(0, count + stride, stride)))
            self.assertLess(len(calls), len(range(0, count + 2 * stride, stride)))
            restored = sum(samples(path) for path in result.values())
            np.testing.assert_allclose(restored, original, atol=1e-7)

    def test_cancel_does_not_load_or_create_outputs(self):
        event = threading.Event(); event.set()
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'out'
            with self.assertRaises(SeparationCancelled):
                QualityFiveStemSeparator().separate('missing.wav', output, cancel_event=event)
            self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_cancel_during_inference_cleans_partial_wavs(self):
        class Cancelled(Controlled):
            def _chunk(self, audio, event):
                event.set()
                raise SeparationCancelled('Cancelled')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            recording(source, 137)
            with self.assertRaises(SeparationCancelled):
                Cancelled().separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertTrue(source.is_file())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
    def test_five_outputs_split_remaining_music_and_reconstruct(self):
        from music_studio.piano import PianoSeparator
        class ControlledPiano(PianoSeparator):
            def _graph(self, name, features, event):
                return np.zeros_like(features[0])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            original = recording(source, 44100)
            with patch('music_studio.roformer.RoformerSeparator', Controlled), patch('music_studio.piano.PianoSeparator', ControlledPiano):
                result = QualityFiveStemSeparator().separate(source, root / 'out')
            self.assertEqual(list(result), ['vocals', 'drums', 'bass', 'piano', 'other'])
            self.assertEqual(set((root / 'out').iterdir()), set(result.values()))
            decoded = {name: samples(path) for name, path in result.items()}
            np.testing.assert_allclose(decoded['vocals'], original * .4, atol=1e-7)
            np.testing.assert_allclose(decoded['drums'], original * .1, atol=1e-7)
            np.testing.assert_allclose(decoded['bass'], original * .2, atol=1e-7)
            np.testing.assert_allclose(decoded['piano'] + decoded['other'], original * .3, atol=1e-7)
            np.testing.assert_allclose(sum(decoded.values()), original, atol=1e-7)

    def test_second_stage_failure_cleans_intermediate_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            source.write_bytes(b'original')
            with patch('music_studio.roformer.RoformerSeparator') as main, patch('music_studio.piano.PianoSeparator') as piano:
                main.return_value.separate.return_value = {'other': root / 'remaining.wav'}
                piano.return_value.separate.side_effect = ValueError('Piano inference failed')
                with self.assertRaisesRegex(ValueError, 'Piano inference failed'):
                    QualityFiveStemSeparator().separate(source, root / 'out')
            self.assertEqual(list((root / 'out').iterdir()), [])
            self.assertEqual(source.read_bytes(), b'original')

    @unittest.skipUnless(os.environ.get('BLAZE_REAL_ROFORMER'), 'Real model explicitly requested')
    def test_real_five_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'mix.wav'
            original = recording(source, 44100)
            result = QualityFiveStemSeparator(os.environ['BLAZE_STEM_MODEL_DIR']).separate(source, root / 'out')
            self.assertEqual(set(result), {'vocals', 'drums', 'bass', 'piano', 'other'})
            decoded = [samples(path) for path in result.values()]
            self.assertTrue(all(np.isfinite(track).all() for track in decoded))
            np.testing.assert_allclose(sum(decoded), original, atol=1e-7)


if __name__ == '__main__':
    unittest.main()
