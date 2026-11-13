"""Offline, explicit ChordMini BTC CL experiment with its own feature contract.

Librosa is an optional candidate dependency, not part of the stable app runtime.
"""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import onnxruntime as ort

from .engine import Analyzer, RATE
from .stem_runtime import StemRuntime
from .verified_session import VerifiedSession

CHECKPOINT_SHA = 'e0a12ca6d881f81e01dfb459b4836ec7dac8d8f87b0170a412b5807256b3a1fc'
ENGINE_VERSION = 'chordmini-cl-librosa011-zero108-stride54-logits1'
MAX_SECONDS = 1800


class ChordMiniBundle:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory/'manifest.json').read_text())
        m = self.manifest
        if (m.get('schema_version') != 1 or m.get('candidate') != 'chordmini-btc-cl'
                or m.get('checkpoint_sha256') != CHECKPOINT_SHA):
            raise ValueError('Incompatible ChordMini candidate.')
        c = m['contract']
        identity = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        if identity != m['frontend_sha256']:
            raise ValueError('ChordMini frontend checksum failed.')
        expected = {'rate':RATE,'hop':2048,'bins':144,'bins_per_octave':24,'fmin':'C1',
                    'librosa':'0.11.0','log_epsilon':1e-6,'normalization_epsilon':1e-8,
                    'window':108,'stride':54,'padding':'raw-feature-zero-before-normalization',
                    'aggregation':'logit','smoothing':False}
        if any(c.get(k) != v for k,v in expected.items()):
            raise ValueError('Unsupported ChordMini preprocessing contract.')
        qualities = ['min','maj','dim','aug','min6','maj6','min7','minmaj7','maj7','7','dim7','hdim7','sus2','sus4']
        labels = [r+':'+q for r in ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'] for q in qualities]+['X','N']
        if (c['labels'] != labels or not np.isfinite([c['mean'],c['std']]).all() or c['std'] <= 0):
            raise ValueError('Invalid ChordMini vocabulary or normalization.')
        self.contract = c
        self.structured = None
        self.engine_version = ENGINE_VERSION
        self.metadata = dict(m['model'], name='ChordMini BTC CL (experimental)', version=m['source_commit'],
                             classes=170, labels=labels, mean=c['mean'], std=c['std'])
        self.manifest['frontend'] = {'sha256':identity}
        self.runtime = StemRuntime()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.network = VerifiedSession(self.directory, m['model'], self.runtime, options, 100*1024**2)

    def close(self):
        self.network.close()

    def predict_features(self, features, check=lambda: None, progress=lambda message: None):
        """Match upstream logit voting: raw-zero pad, then normalize, overlap54."""
        features = np.asarray(features, dtype=np.float32)
        if features.ndim != 2 or features.shape[1] != 144 or not len(features) or not np.isfinite(features).all():
            raise ValueError('Invalid ChordMini features.')
        count = len(features)
        padded = np.pad(features, ((0,(-count)%108),(0,0)))
        votes = np.zeros((count,170),dtype=np.float32)
        for start in range(0,len(padded)-108+1,54):
            check()
            value = np.asarray((padded[start:start+108][None]-np.float32(self.contract['mean'])) /
                               (np.float32(self.contract['std'])+np.float32(1e-8)), dtype=np.float32)
            logits = self.network.run(['logits'], {'features':value})[0]
            check()
            if logits.shape != (1,108,170) or not np.isfinite(logits).all():
                raise ValueError('ChordMini returned invalid predictions.')
            valid = min(108,count-start)
            votes[start:start+valid] += logits[0,:valid]
            progress(f'Finding chords · {min(count,start+108)*2048/RATE:.1f} seconds analysed')
        # Hard labels match upstream logit sum; uncalibrated scores omitted.
        return votes.argmax(axis=1)


class ChordMiniAnalyzer(Analyzer):
    def _analyze(self, source, progress=lambda message: None):
        try:
            import librosa
        except ImportError as error:
            raise ValueError('Install the local ChordMini candidate dependencies first.') from error
        if librosa.__version__ != self.bundle.contract['librosa']:
            raise ValueError('ChordMini requires its pinned librosa 0.11.0 frontend.')
        start = time.perf_counter()
        path = Path(source).resolve(strict=True)
        checksum = self._source_digest(path)
        self.timings = {'checksum_seconds':time.perf_counter()-start}
        phase = time.perf_counter()
        self.check()
        progress('Reading audio for the experimental chord model…')
        # Full-track CQT follows upstream evaluation, not Blaze legacy edge padding.
        audio, rate = librosa.load(path, sr=RATE, mono=True, duration=MAX_SECONDS+1)
        self.timings['audio_load_seconds'] = time.perf_counter()-phase
        self.check()
        if not len(audio) or len(audio)/rate > MAX_SECONDS or not np.isfinite(audio).all():
            raise ValueError('The experimental chord model accepts recordings up to 30 minutes.')
        progress('Preparing chord features…')
        phase = time.perf_counter()
        cqt = librosa.cqt(audio,sr=RATE,n_bins=144,bins_per_octave=24,hop_length=2048,fmin=librosa.note_to_hz('C1'))
        features = np.log(np.abs(cqt)+1e-6).T.astype(np.float32)
        del cqt
        self.timings['features_seconds'] = time.perf_counter()-phase
        phase = time.perf_counter()
        self.check()
        indexes = self.bundle.predict_features(features,self.check,progress)
        self.timings['inference_seconds'] = time.perf_counter()-phase
        del features
        duration = len(audio)/RATE
        events = []
        for i,index in enumerate(indexes):
            left = i*2048/RATE
            if left >= duration:
                break
            right = min(duration,(i+1)*2048/RATE)
            chord = self.bundle.metadata['labels'][int(index)]
            if events and events[-1]['chord'] == chord:
                events[-1]['end'] = right
            else:
                events.append({'start':left,'end':right,'chord':chord,'model_score':None,'edited':False})
        boundaries = np.linspace(0,len(audio),min(1024,len(audio))+1,dtype=int)
        waveform = [float(np.max(np.abs(audio[a:b]))) for a,b in zip(boundaries,boundaries[1:])]
        from .chords import estimate_key
        metadata = self.bundle.metadata
        return {'schema_version':1,'engine_version':ENGINE_VERSION,'audio_file':path.name,
                'source_sha256':checksum,'duration':duration,'key':estimate_key(events),
                'tempo_bpm':None,'beats':[],'waveform':waveform,'chords':events,
                'model':{'name':metadata['name'],'version':metadata['version'],'sha256':metadata['sha256'],
                         'frontend_sha256':self.bundle.manifest['frontend']['sha256']},
                'confidence_kind':'uncalibrated_model_score','analysis_seconds':round(time.perf_counter()-start,3)}
