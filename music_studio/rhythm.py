"""Offline Beat This! inference using NumPy and ONNX Runtime only.

Frontend, overlap handling and peak decoder follow the MIT-licensed upstream.
No weights are downloaded at runtime. Meter is a separate consistency estimate.
"""
from pathlib import Path
import hashlib
import io
import json
import numpy as np
import onnxruntime as ort
from .meter import estimate_meter


class MelAccumulator:
    def __init__(self,window,filters):
        self.window,self.filters=window,filters
        self.buffer=np.empty(0,dtype=np.float32)
        self.tail=np.empty(0,dtype=np.float32)
        self.features=[]
        self.samples=0
        self.initial=True
        self.audible=False

    def feed(self,pcm):
        pcm=np.asarray(pcm,dtype=np.float32)
        self.samples+=len(pcm)
        self.audible |= float(np.max(np.abs(pcm),initial=0))>1e-5
        self.tail=np.concatenate((self.tail,pcm))[-513:].copy()
        self.buffer=np.concatenate((self.buffer,pcm))
        if self.initial:
            if len(self.buffer)<513:return
            self.buffer=np.concatenate((self.buffer[1:513][::-1],self.buffer))
            self.initial=False
        self._extract()

    def _extract(self):
        if len(self.buffer)<1024:return
        windows=np.lib.stride_tricks.sliding_window_view(self.buffer,1024)[::441]
        magnitude=(np.abs(np.fft.rfft(windows*self.window,axis=1))/32).astype(np.float32)
        self.features.append(np.log1p(1000*(magnitude@self.filters)).astype(np.float32))
        self.buffer=self.buffer[len(windows)*441:].copy()

    def finish(self):
        if self.initial:return np.empty((0,128),dtype=np.float32)
        self.buffer=np.concatenate((self.buffer,self.tail[-2::-1]))
        self._extract()
        result=np.concatenate(self.features) if self.features else np.empty((0,128),dtype=np.float32)
        self.features.clear()
        return result[:self.samples//441+1]


def peak_times(logits):
    padded=np.pad(np.asarray(logits),3,constant_values=-np.inf)
    maxima=np.lib.stride_tricks.sliding_window_view(padded,7).max(axis=1)
    indexes=np.flatnonzero((logits==maxima)&(logits>0))
    peaks=[];mean=None;count=0
    for index in indexes:
        if mean is not None and index-mean<=1:
            count+=1;mean+=(int(index)-mean)/count
        else:
            if mean is not None:peaks.append(mean/50)
            mean=float(index);count=1
    if mean is not None:peaks.append(mean/50)
    return np.asarray(peaks,dtype=np.float64)


class RhythmDetector:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.manifest=json.loads((self.directory/'rhythm_manifest.json').read_text(encoding='utf-8'))
        if any(self.manifest.get(k)!=v for k,v in {'schema_version':1,'sample_rate':22050,'hop_length':441,'n_fft':1024,'fps':50,'chunk_frames':1500,'border_frames':6}.items()):
            raise ValueError('Incompatible offline rhythm model.')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        ort.disable_telemetry_events()
        self.network=ort.InferenceSession(self._asset('network'),sess_options=options,providers=['CPUExecutionProvider'])
        with np.load(io.BytesIO(self._asset('frontend')),allow_pickle=False) as frontend:
            self.window,self.filters=frontend['window'].copy(),frontend['filter'].copy()
        if self.window.shape!=(1024,) or self.filters.shape!=(513,128):raise ValueError('Invalid rhythm frontend.')
        self.audio=MelAccumulator(self.window,self.filters)

    def _asset(self,key):
        metadata=self.manifest[key];name=metadata['file']
        if Path(name).name!=name:raise ValueError('Invalid rhythm asset path.')
        path=self.directory/name
        if not path.is_file() or path.stat().st_size>200*1024**2:raise ValueError('Offline rhythm asset missing or too large.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=metadata['sha256']:raise ValueError('Rhythm asset verification failed.')
        return data

    def finish(self,duration,check=lambda:None,progress=lambda message:None):
        spect=self.audio.finish()
        if len(spect)<200 or not self.audio.audible:
            return self._result([],[],duration)
        size=len(spect);starts=np.arange(-6,size-6,1488,dtype=int)
        if size>1488:starts[-1]=size-1494
        predictions=[np.full(size,-1000,dtype=np.float32) for _ in range(2)]
        filled=np.zeros(size,dtype=bool)
        for number,start in enumerate(starts):
            check();progress(f'Finding beats and meter locally · {number+1} / {len(starts)}')
            chunk=spect[max(start,0):min(start+1500,size)]
            chunk=np.pad(chunk,((max(0,-start),max(0,min(6,start+1500-size))),(0,0)))
            outputs=self.network.run(None,{'spect':chunk[None].astype(np.float32)})
            a,b=start+6,start+len(chunk)-6
            unused=~filled[a:b]
            for channel,output in zip(predictions,outputs):channel[a:b][unused]=output[0,6:-6][unused]
            filled[a:b]=True
        if not filled.all():raise ValueError('Incomplete rhythm prediction.')
        beat=peak_times(predictions[0]);downbeat=peak_times(predictions[1])
        beat=beat[beat<duration]
        if len(beat):downbeat=np.unique([beat[np.argmin(np.abs(beat-t))] for t in downbeat if t<duration])
        else:downbeat=[]
        return self._result(beat,downbeat,duration)

    def _result(self,beats,downbeats,duration):
        beats=[round(float(t),4) for t in beats];downbeats=[round(float(t),4) for t in downbeats]
        intervals=np.diff(beats)
        tempo=round(float(60/np.median(intervals)),1) if len(intervals)>2 else None
        return {'beats':beats,'downbeats':downbeats,'tempo_bpm':tempo,'meter':estimate_meter(beats,downbeats,duration),
                'rhythm_model':{k:self.manifest[k] for k in ('name','version','source','license')},
                'rhythm_model_sha256':self.manifest['network']['sha256']}
