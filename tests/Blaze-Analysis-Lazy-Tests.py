"""Verified cache hits must not create inference sessions or trust changed assets."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from music_studio.engine import ModelBundle, waveform_peaks, Analyzer, AnalysisCancelled
from music_studio.verified_session import VerifiedSession


class LazyTests(unittest.TestCase):
    def test_spectral_blocks_skip_zero_padding_without_changing_fft_values(self):
        from music_studio import lv_frontend as lv
        rng=np.random.default_rng(181);fft,hop=512,64;window=np.hanning(513)[:-1]
        for dtype in (np.float32,np.float64):
            for count in (1,512,65537):
                audio=rng.normal(size=count*2).astype(dtype)[::2]
                audio.setflags(write=False)
                padded=np.pad(audio,(fft//2,fft//2))
                windows=np.lib.stride_tricks.sliding_window_view(padded,fft)[::hop]
                expected=[np.fft.rfft(windows[start:start+256]*window,axis=-1).T.astype(np.complex64) for start in range(0,len(windows),256)]
                with patch.object(np,'pad',wraps=np.pad) as padding:
                    actual=list(lv._spectral_blocks(audio,fft,hop,window))
                self.assertTrue(all(any(call.args[1]) for call in padding.call_args_list))
                if len(actual)>3:self.assertLess(padding.call_count,len(actual))
                self.assertEqual(len(actual),len(expected))
                for index,((start,got),want) in enumerate(zip(actual,expected)):
                    self.assertEqual(start,index*256)
                    self.assertEqual(got.tobytes(),want.tobytes())

    def test_pcm_feed_preserves_bytes_counts_and_strided_input(self):
        from music_studio.structured import StructuredRecognizer
        rng=np.random.default_rng(180)
        recognizer=StructuredRecognizer.__new__(StructuredRecognizer)
        recognizer.audio=io.BytesIO();recognizer.samples=0
        expected=bytearray();count=0
        for dtype in (np.float32,np.float64):
            for size in (0,1,31,110592):
                source=rng.normal(size=size*2).astype(dtype)[::2]
                source.setflags(write=False)
                expected.extend(np.asarray(source,dtype=np.float32).tobytes())
                count+=len(source)
                recognizer.feed(source)
                self.assertEqual(recognizer.audio.getvalue(),bytes(expected))
                self.assertEqual(recognizer.samples,count)

    def test_cached_sounding_names_preserve_original_cleanup_and_scores(self):
        from music_studio.structured import stabilize_equivalent_names
        from music_studio.chords import notes
        def reference_stabilize(frames):
            """Name one uninterrupted sounding set consistently; retain slash bass."""
            start=0
            while start<len(frames):
                label=frames[start]['chord']
                if label in ('X','N') or '/' in label:start+=1;continue
                sounding=notes(label);end=start+1
                while end<len(frames):
                    next_label=frames[end]['chord']
                    if next_label in ('X','N') or '/' in next_label or notes(next_label)!=sounding:break
                    end+=1
                support={}
                for frame in frames[start:end]:
                    support[frame['chord']]=support.get(frame['chord'],0)+(frame['end']-frame['start'])*max(.1,frame['model_score'] or 0)
                chosen=max(support,key=support.get)
                for frame in frames[start:end]:frame['chord']=chosen
                start=end
            return frames
        rng=np.random.default_rng(179)
        groups=[['C:maj6','A:min7'],['C:dim7','D#:dim7','F#:dim7','A:dim7'],['C:maj'],['C:maj/E'],['N'],['X']]
        for count in (0,1,31,8000):
            frames=[]
            for index in range(count):
                choices=groups[(index//31)%len(groups)]
                label=choices[index%len(choices)]
                frames.append({'start':index*.023,'end':(index+1)*.023,'chord':label,
                               'model_score':None if index%7==0 else float(rng.uniform(0,1)),'edited':False})
            expected=reference_stabilize([dict(row) for row in frames])
            with patch('music_studio.structured.notes',wraps=notes) as parsing:
                actual=stabilize_equivalent_names([dict(row) for row in frames])
            self.assertEqual(actual,expected)
            self.assertLessEqual(parsing.call_count,len({row['chord'] for row in frames}))
        with self.assertRaises(ValueError):
            stabilize_equivalent_names([{'chord':'not-a-chord'}])

    def test_consumed_onset_magnitudes_preserve_flux_and_cross_chunk_state(self):
        from music_studio.engine import _consume_onset_spectrum
        rng=np.random.default_rng(178)
        for dtype in (np.float32,np.float64):
            previous=np.zeros(1025,dtype=dtype)
            for count in (1,2,108,861):
                spectrum=rng.uniform(0,100,(count,1025)).astype(dtype)
                spectrum[0]=0
                reference=spectrum.copy();prior=previous.copy()
                preceding=np.vstack((previous,reference[:-1]))
                expected=np.maximum(0,reference-preceding).sum(axis=1)/np.maximum(1e-8,reference.sum(axis=1))
                actual,last=_consume_onset_spectrum(spectrum,previous)
                self.assertEqual(actual.dtype,expected.dtype)
                self.assertEqual(actual.tobytes(),expected.tobytes())
                self.assertEqual(last.tobytes(),reference[-1].tobytes())
                self.assertEqual(previous.tobytes(),prior.tobytes())
                spectrum[:]=0
                self.assertEqual(last.tobytes(),reference[-1].tobytes())
                previous=last

    def test_shared_context_peaks_preserve_baseline_silence_windows(self):
        from music_studio.engine import context_silence_mask
        rng=np.random.default_rng(176)
        for dtype in (np.float32,np.float64):
            for count in (1,2047,2048,2049,4096,8193,221184):
                audio=np.zeros(count,dtype=dtype)
                audio[::2051]=rng.choice([-1e-5,1e-5,1e-6,.1],len(audio[::2051]))
                for values in (audio,audio[::2]):
                    expected=np.array([float(np.max(np.abs(values[max(0,i*2048-4096):min(len(values),i*2048+4096)]),initial=0))<1e-5 for i in range((len(values)+2047)//2048)])
                    np.testing.assert_array_equal(context_silence_mask(values),expected)
        self.assertEqual(len(context_silence_mask(np.empty(0))),0)

    def test_factored_observation_logs_preserve_every_score_and_input(self):
        from music_studio.structured import observation_scores
        rng=np.random.default_rng(175)
        widths=(73,13,4,4,3,3)
        components=np.stack([rng.integers(width,size=1381) for width in widths],axis=1)
        columns=rng.integers(97,size=1381);baseline_frames=np.arange(260)//4
        for dtype in (np.float32,np.float64):
            priors=rng.uniform(-1e-7,1,(65,97)).astype(dtype);priors[0]=0
            heads=[rng.uniform(-1e-7,1,(260,width)).astype(dtype) for width in widths]
            for head in heads:head[0]=1e-7
            saved=[value.copy() for value in [priors,*heads]]
            for start,end in ((0,1),(0,7),(0,31),(0,128),(128,256),(256,260)):
                score=1.2*np.log(np.maximum(priors[baseline_frames[start:end]][:,columns],1e-7))
                for k,head in enumerate(heads):
                    score+=(1.0 if k==0 else .65)*np.log(np.maximum(head[start:end,components[:,k]],1e-7))
                actual=observation_scores(priors,columns,baseline_frames,heads,components,start,end)
                self.assertEqual(actual.dtype,score.dtype)
                self.assertEqual(actual.tobytes(),score.tobytes())
            for actual,original in zip([priors,*heads],saved):np.testing.assert_array_equal(actual,original)

    def test_batched_silence_mask_preserves_boundaries_thresholds_and_cancellation(self):
        from music_studio.structured import silence_mask
        rng=np.random.default_rng(174)
        for dtype in (np.float32,np.float64):
            for count in (1,511,512,513,65537,200003):
                with self.subTest(dtype=dtype,count=count):
                    audio=np.zeros(count,dtype=dtype)
                    audio[::1027]=rng.choice([-1e-5,1e-5,1e-6,0],size=len(audio[::1027]))
                    times=np.arange((count+511)//512+2)*512/22050
                    expected=np.array([np.max(np.abs(audio[int(t*22050):min(len(audio),int(t*22050)+512)]),initial=0)<1e-5 for t in times])
                    np.testing.assert_array_equal(silence_mask(audio,times),expected)
                    # A strided view must make the same decision as scalar slicing.
                    view=audio[::2]
                    expected=np.array([np.max(np.abs(view[int(t*22050):min(len(view),int(t*22050)+512)]),initial=0)<1e-5 for t in times])
                    np.testing.assert_array_equal(silence_mask(view,times),expected)
        np.testing.assert_array_equal(silence_mask(np.empty(0),np.array([0.])),[True])
        self.assertEqual(len(silence_mask(audio,np.empty(0))),0)
        with self.assertRaises(AnalysisCancelled):
            silence_mask(audio,times,check=lambda:(_ for _ in ()).throw(AnalysisCancelled()))

    def test_sparse_feature_rows_are_reused_without_changing_response_values(self):
        from music_studio import lv_frontend as lv
        def reference_spectral_blocks(y: object, nfft: int, hop: int, window: object,
                             block_frames: int = 256):
            """STFT blocks without constructing an audio-size padded copy."""
            count = 1 + len(y) // hop
            half = nfft // 2
            for frame in range(0, count, block_frames):
                last = min(count, frame + block_frames)
                left, right = frame * hop - half, (last - 1) * hop + half
                signal = y[max(0, left):min(len(y), right)]
                signal = np.pad(signal, (max(0, -left), max(0, right - len(y))))
                frames = np.lib.stride_tricks.sliding_window_view(signal, nfft)[::hop]
                yield frame, np.fft.rfft(frames * window, axis=-1).T.astype(np.complex64)
        def reference_project(filters: object, spectrum: object) -> object:
            # Sparse rows are typically only tens of frequency bins, so this avoids
            # a large dense GEMM and any SciPy dependency.
            output = np.empty((len(filters), spectrum.shape[1]), np.complex64)
            for row, coefficients in enumerate(filters):
                indices = np.flatnonzero(coefficients)
                for start in range(0, spectrum.shape[1], 512):
                    output[row, start:start + 512] = np.sum(
                        coefficients[indices, None] * spectrum[indices, start:start + 512],
                        axis=0, dtype=np.complex64)
            return output
        def reference_response(y: object, filters: object, nfft: int, hop: int,
                      window: object, magnitude_only: bool = False,
                      destination=None, check=lambda: None) -> object:
            result = np.empty((len(filters), 1 + len(y) // hop), np.float32) if destination is None else destination
            for start, spectrum in reference_spectral_blocks(y, nfft, hop, window):
                check()
                if magnitude_only:
                    spectrum = np.abs(spectrum)
                projected = np.abs(reference_project(filters, spectrum))
                count = min(projected.shape[1], result.shape[1] - start)
                if count > 0:
                    result[:, start:start + count] = projected[:, :count]
            return result
        rng=np.random.default_rng(173)
        filters=np.zeros((7,257),np.complex64)
        for row in filters[1:]:
            indices=rng.choice(257,size=8,replace=False)
            row[indices]=(rng.normal(size=8)+1j*rng.normal(size=8)).astype(np.complex64)
        audio=rng.normal(size=20003).astype(np.float32);window=np.hanning(513)[:-1]
        for magnitude in (False,True):
            expected=reference_response(audio,filters,512,16,window,magnitude)
            # A relative bound on the final magnitude is invalid near complex
            # cancellation. Bound roundoff by the sum of input term magnitudes.
            # Each of the two FP32 paths has at most 4 product, 8 reduction and
            # 2 magnitude rounding steps; 32 eps conservatively covers both.
            bounds=np.empty_like(expected,dtype=np.float64)
            epsilon=np.finfo(np.float32).eps
            gamma=32*epsilon/(1-32*epsilon)
            for start,spectrum in reference_spectral_blocks(audio,512,16,window):
                terms=np.abs(filters.astype(np.complex128))@np.abs(spectrum.astype(np.complex128))
                bounds[:,start:start+terms.shape[1]]=gamma*terms
            with patch.object(np,'flatnonzero',wraps=np.flatnonzero) as prepare:
                actual=lv._response(audio,filters,512,16,window,magnitude)
            self.assertEqual(prepare.call_count,len(filters))
            self.assertTrue(np.all(np.abs(actual.astype(np.float64)-expected)<=bounds))
            destination=np.empty((7,expected.shape[1]*2),np.float32)[:,::2]
            self.assertIs(lv._response(audio,filters,512,16,window,magnitude,destination),destination)
            self.assertTrue(np.all(np.abs(destination.astype(np.float64)-expected)<=bounds))
            # The precision bound must still reject a substantive gain error.
            self.assertFalse(np.all(np.abs(expected.astype(np.float64)*1.001-expected)<=bounds))
        with self.assertRaises(AnalysisCancelled):
            lv._response(audio,filters,512,16,window,check=lambda:(_ for _ in ()).throw(AnalysisCancelled()))

    def test_resampling_reuses_kernel_fft_without_changing_samples_or_cancellation(self):
        from music_studio.lv_frontend import PortableLVFrontend
        rng = np.random.default_rng(153)
        frontend = PortableLVFrontend.__new__(PortableLVFrontend)
        frontend.kernel = np.hanning(191)
        frontend.kernel /= frontend.kernel.sum()
        frontend.half = (len(frontend.kernel)-1)//2

        def reference(y):
            result = np.empty((len(y)+1)//2, np.float32)
            for start in range(0,len(y),65536):
                end=min(len(y),start+65536)
                left,right=start-frontend.half,end+frontend.half
                signal=np.pad(y[max(0,left):min(len(y),right)],(max(0,-left),max(0,right-len(y))))
                nfft=1 << (len(signal)+len(frontend.kernel)-2).bit_length()
                convolved=np.fft.irfft(np.fft.rfft(signal,n=nfft)*np.fft.rfft(frontend.kernel,n=nfft),n=nfft)
                result[start//2:(end+1)//2]=convolved[2*frontend.half:2*frontend.half+end-start:2]*np.sqrt(2)
            return result

        for count in (1,65535,65536,65537,3*65536+13):
            with self.subTest(count=count):
                audio=rng.normal(size=count).astype(np.float32)
                expected=reference(audio)
                transform=np.fft.rfft
                kernel_sizes=[]
                def tracked(value, *args, **kwargs):
                    if value is frontend.kernel:kernel_sizes.append(kwargs['n'])
                    return transform(value,*args,**kwargs)
                with patch.object(np.fft,'rfft',side_effect=tracked):
                    actual=frontend._down(audio)
                self.assertEqual(actual.tobytes(),expected.tobytes())
                self.assertEqual(len(kernel_sizes),len(set(kernel_sizes)))
                with tempfile.TemporaryDirectory() as directory:
                    cached=frontend._down(audio,Path(directory)/'resampled.f32')
                    self.assertEqual(cached.tobytes(),expected.tobytes())
                    del cached
        frontend.kernel *= .5
        self.assertEqual(frontend._down(audio).tobytes(),reference(audio).tobytes())
        with self.assertRaises(AnalysisCancelled):
            frontend._down(audio,check=lambda:(_ for _ in ()).throw(AnalysisCancelled()))

    def test_vectorized_waveform_preserves_peaks_for_silence_edges_and_strided_blocks(self):
        rng = np.random.default_rng(18)
        blocks = rng.normal(size=(867, 512)).astype(np.float32)[:, ::2]
        blocks[0] = 0
        blocks[1, 0] = -3
        blocks[-1, -1] = 4
        expected = [float(np.max(np.abs(block))) for block in blocks]
        self.assertEqual(waveform_peaks(blocks), expected)
        self.assertEqual(waveform_peaks(np.empty((0, 256), dtype=np.float32)), [])

    def test_private_verified_copy_skips_second_read_but_changed_file_is_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.wav'
            path.write_bytes(b'original recording')
            analyzer = Analyzer(None, 'ffmpeg')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            analyzer.verified_input = (path, analyzer.input_stamp(path), expected)
            with patch.object(Path, 'open', side_effect=AssertionError('Redundant source read')):
                self.assertEqual(analyzer._source_digest(path), expected)
            path.write_bytes(b'replaced recording')
            self.assertEqual(analyzer._source_digest(path), hashlib.sha256(path.read_bytes()).hexdigest())
            other = Path(directory) / 'other.wav'
            other.write_bytes(b'other recording')
            self.assertEqual(analyzer._source_digest(other), hashlib.sha256(other.read_bytes()).hexdigest())
            analyzer.cancel()
            with self.assertRaises(AnalysisCancelled):
                analyzer._source_digest(path)

    def test_ensemble_buffers_match_frozen_multi_context_output_without_mutating_logits(self):
        from music_studio.structured import StructuredRecognizer
        def reference_predict_features(self,features,check=lambda:None,progress=lambda message:None):
                """Overlapping contexts keep memory bounded and retain every frame."""
                size=len(features);outputs=None;weights=np.zeros(size,dtype=np.float32)
                context=1292;stride=1034
                for start in range(0,size,stride):
                    check();end=min(size,start+context)
                    value=np.ascontiguousarray(features[start:end][None],dtype=np.float32)
                    average=None
                    for net in self.networks:
                        check();raw=net.run(None,{'features':value})
                        probs=[]
                        for head in raw:
                            head=head-head.max(axis=1,keepdims=True);head=np.exp(head);head/=head.sum(axis=1,keepdims=True);probs.append(head)
                        if average is None:average=probs
                        else:
                            for total,head in zip(average,probs):total+=head
                    for head in average:head/=len(self.networks)
                    if outputs is None:outputs=[np.zeros((size,a.shape[1]),dtype=np.float32) for a in average]
                    weight=np.minimum(np.minimum(np.arange(end-start)+1,np.arange(end-start,0,-1)),129)/129
                    for dest,head in zip(outputs,average):dest[start:end]+=head*weight[:,None]
                    weights[start:end]+=weight
                    progress(f'Advanced chord ensemble · {end*512/22050:.1f} seconds analysed')
                    if end==size:break
                return [head/weights[:,None] for head in outputs]
        rng=np.random.default_rng(162)
        logits=[[rng.normal(size=(1292,width)).astype(np.float32) for width in (73,13,4,4,3,3)] for _ in range(5)]
        saved=[[head.copy() for head in fold] for fold in logits]
        engine=StructuredRecognizer.__new__(StructuredRecognizer)
        engine.networks=[Mock(run=Mock(side_effect=lambda _,feed,fold=fold:[head[:feed['features'].shape[1]] for head in fold])) for fold in logits]
        for count in (31,1292,1293,2600):
            features=np.zeros((count,252),np.float32)
            expected=reference_predict_features(engine,features)
            actual=engine.predict_features(features)
            for got,want in zip(actual,expected):
                self.assertEqual(got.dtype,want.dtype)
                self.assertEqual(got.tobytes(),want.tobytes())
        for fold,original in zip(logits,saved):
            for head,prior in zip(fold,original):np.testing.assert_array_equal(head,prior)

    def test_streamed_ensemble_matches_original_mean(self):
        from music_studio.structured import StructuredRecognizer
        rng = np.random.default_rng(81)
        raw = [[rng.normal(size=(31, width)).astype(np.float32) for width in (12, 8, 4, 3, 6, 2)] for _ in range(5)]
        votes = []
        for outputs in raw:
            probs = []
            for head in outputs:
                head = np.exp(head - head.max(axis=1, keepdims=True))
                head /= head.sum(axis=1, keepdims=True)
                probs.append(head)
            votes.append(probs)
        expected = [np.mean([vote[k] for vote in votes], axis=0) for k in range(6)]
        engine = StructuredRecognizer.__new__(StructuredRecognizer)
        engine.networks = [Mock(run=Mock(return_value=value)) for value in raw]
        actual = engine.predict_features(np.zeros((31, 252), dtype=np.float32))
        # Context weighting adds the same float32 roundoff to both paths.
        weight = np.minimum(np.minimum(np.arange(31)+1, np.arange(31,0,-1)),129)/129
        for got, want in zip(actual, expected):
            weighted = np.asarray(want * weight[:,None], dtype=np.float32)
            weighted /= weight.astype(np.float32)[:,None]
            np.testing.assert_array_equal(got, weighted)

    def test_verified_session_defers_load_reuses_and_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.onnx'
            path.write_bytes(b'verified')
            metadata = {'file': path.name, 'sha256': hashlib.sha256(b'verified').hexdigest()}
            runtime = Mock()
            session = VerifiedSession(directory, metadata, runtime, None, 100)
            runtime.session.assert_not_called()
            session.run(None, {})
            session.run(None, {})
            runtime.session.assert_called_once_with(b'verified', None, metadata['sha256'])
            session.close()
            path.write_bytes(b'replaced')
            with self.assertRaisesRegex(ValueError, 'verification'):
                session.run(None, {})
            self.assertEqual(runtime.session.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'verification'):
                VerifiedSession(directory, metadata, runtime, None, 100)

    def test_powerful_bundle_validates_every_asset_without_opening_neural_sessions(self):
        original = Path(__file__).resolve().parents[1] / 'music_studio/models'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            basic = json.loads((original / 'manifest.json').read_text())
            structured = json.loads((original / 'structured_manifest.json').read_text())
            assets = [basic['frontend'], *basic['models'].values(), structured['frontend'], *structured['models']]
            for asset in assets:
                data = asset['file'].encode()
                (root / asset['file']).write_bytes(data)
                asset['sha256'] = hashlib.sha256(data).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(basic))
            (root / 'structured_manifest.json').write_text(json.dumps(structured))
            with patch('music_studio.engine.StemRuntime') as runtime, \
                    patch('music_studio.stem_runtime.StemRuntime') as ensemble_runtime, \
                    patch('music_studio.structured.PortableLVFrontend'):
                bundle = ModelBundle(root, 'powerful')
                expected = [basic['models']['extended']['sha256'], structured['frontend']['sha256'],
                            *(asset['sha256'] for asset in structured['models'])]
                self.assertEqual(bundle.metadata['sha256'], hashlib.sha256(''.join(expected).encode()).hexdigest())
                runtime.return_value.session.assert_not_called()
                ensemble_runtime.return_value.session.assert_not_called()
                bundle.close()
                (root / structured['models'][-1]['file']).write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError, 'verification'):
                    ModelBundle(root, 'powerful')
                ensemble_runtime.return_value.session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
