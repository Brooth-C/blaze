"""MIT pretrained chord components fused with BTC and sequence decoding.

Weights are from Music X Lab's released five-fold ensemble. Only local,
checksum-verified ONNX files are used. Acoustic support is not calibrated.
"""
from pathlib import Path
import hashlib,json,tempfile
import numpy as np
from .lv_frontend import PortableLVFrontend
from .evidence import grouped_candidates
from .chords import notes

CORE_FAMILIES={
 'maj':['maj','maj6','maj7','7'], 'min':['min','min6','min7','minmaj7'],
 'dim':['dim','dim7','hdim7'], 'aug':['aug'], 'sus2':['sus2'], 'sus4':['sus4']}
FAMILY={'maj6':'maj','maj7':'maj','7':'maj','9':'maj','maj9':'maj','11':'maj','13':'maj','maj13':'maj',
 'min6':'min','min7':'min','minmaj7':'min','min9':'min','min11':'min','min13':'min','dim7':'dim','hdim7':'dim','7sus4':'sus4'}
PARENT={'9':'7','11':'7','13':'7','maj9':'maj7','maj13':'maj7','min9':'min7','min11':'min7','min13':'min7','7sus4':'sus4'}


def sequence_decode(emissions,penalties,beam=20,check=lambda:None):
    """Beam Viterbi with soft change costs; every frame may change chord."""
    history=[];previous=np.empty(0,dtype=np.int32);scores=np.empty(0,dtype=np.float64)
    for t,row in enumerate(emissions):
        if t%256==0:check()
        top=np.argpartition(row,-min(beam,len(row)))[-beam:]
        ids=np.unique(np.concatenate((top,previous))).astype(np.int32)
        if not len(previous):
            values=row[ids].astype(np.float64);parents=np.full(len(ids),-1,dtype=np.int16)
        else:
            best=int(np.argmax(scores));lookup={int(i):n for n,i in enumerate(previous)}
            values=np.empty(len(ids));parents=np.empty(len(ids),dtype=np.int16)
            for n,i in enumerate(ids):
                stay=lookup.get(int(i));changed=scores[best]-penalties[t]
                if stay is not None and scores[stay]>=changed:parents[n]=stay;values[n]=scores[stay]+row[i]
                else:parents[n]=best;values[n]=changed+row[i]
        retained=np.argsort(values)[-beam:];previous=ids[retained];scores=values[retained]
        scores-=scores.max();history.append((previous.copy(),parents[retained].copy()))
    if not history:return np.empty(0,dtype=np.int32)
    cursor=int(np.argmax(scores));path=np.empty(len(history),dtype=np.int32)
    for t in range(len(history)-1,-1,-1):
        ids,parents=history[t];path[t]=ids[cursor];cursor=int(parents[cursor])
    return path


def stabilize_equivalent_names(frames):
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


class StructuredRecognizer:
    def __init__(self,directory):
        # Android shares the exact NumPy decoder while Java owns ORT sessions.
        # Importing this module therefore does not require Python ORT.
        import onnxruntime as ort
        self.directory=Path(directory)
        self.manifest=json.loads((self.directory/'structured_manifest.json').read_text(encoding='utf-8'))
        if self.manifest.get('schema_version')!=1 or self.manifest.get('feature_size')!=252 or len(self.manifest['models'])!=5:
            raise ValueError('Invalid structured chord model bundle.')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL;ort.disable_telemetry_events()
        self.networks=[ort.InferenceSession(self._asset(a),sess_options=options,providers=['CPUExecutionProvider']) for a in self.manifest['models']]
        self._asset(self.manifest['frontend'])
        self.frontend=PortableLVFrontend(self.directory/self.manifest['frontend']['file'])
        self.labels=[a['label'] for a in self.manifest['labels']]
        self.components=np.asarray([a['components'] for a in self.manifest['labels']],dtype=np.int32)
        self.components[:,1]+=1
        if self.components.shape!=(len(self.labels),6) or np.any(self.components<0):raise ValueError('Invalid chord component vocabulary.')
        self.audio=tempfile.TemporaryFile();self.samples=0

    def _asset(self,metadata):
        name=metadata['file']
        if Path(name).name!=name:raise ValueError('Invalid structured asset path.')
        path=self.directory/name
        if not path.is_file() or path.stat().st_size>100*1024**2:raise ValueError('Structured model is missing or too large.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=metadata['sha256']:raise ValueError('Structured model verification failed.')
        return data

    def feed(self,pcm):
        self.audio.write(np.asarray(pcm,dtype=np.float32).tobytes());self.samples+=len(pcm)

    def close(self):self.audio.close()

    def begin(self):
        self.close();self.audio=tempfile.TemporaryFile();self.samples=0

    def features(self):
        self.audio.flush()
        pcm=np.memmap(self.audio,dtype=np.float32,mode='r',shape=(self.samples,))
        try:return self.frontend.extract(pcm)[:,18:270],pcm
        except BaseException:del pcm;raise

    def predict_features(self,features,check=lambda:None,progress=lambda message:None):
        """Overlapping contexts keep memory bounded and retain every frame."""
        size=len(features);outputs=None;weights=np.zeros(size,dtype=np.float32)
        context=1292;stride=1034
        for start in range(0,size,stride):
            check();end=min(size,start+context)
            value=np.ascontiguousarray(features[start:end][None],dtype=np.float32)
            votes=[]
            for net in self.networks:
                check();raw=net.run(None,{'features':value})
                probs=[]
                for head in raw:
                    head=head-head.max(axis=1,keepdims=True);head=np.exp(head);head/=head.sum(axis=1,keepdims=True);probs.append(head)
                votes.append(probs)
            average=[np.mean([v[k] for v in votes],axis=0) for k in range(6)]
            if outputs is None:outputs=[np.zeros((size,a.shape[1]),dtype=np.float32) for a in average]
            weight=np.minimum(np.minimum(np.arange(end-start)+1,np.arange(end-start,0,-1)),129)/129
            for dest,head in zip(outputs,average):dest[start:end]+=head*weight[:,None]
            weights[start:end]+=weight
            progress(f'Advanced chord ensemble · {end*512/22050:.1f} seconds analysed')
            if end==size:break
        return [head/weights[:,None] for head in outputs]

    def decode(self,heads,baseline,baseline_labels,duration,beats,pcm,check=lambda:None):
        count=min(len(heads[0]),int(np.ceil(duration*22050/512)))
        times=np.arange(count)*512/22050
        lookup={label:i for i,label in enumerate(baseline_labels)}
        baseline_frames=np.minimum((times*22050/2048).astype(int),len(baseline)-1)
        groups=[];group_lookup={};prior_columns=[]
        # A shared root/triad prior leaves the extension decision to the ensemble.
        for n,label in enumerate(self.labels):
            if label=='N':key=((lookup['N'],),(),False)
            else:
                root,q=label.split('/')[0].split(':');family=FAMILY.get(q,q)
                family_indexes=tuple(lookup[root+':'+name] for name in CORE_FAMILIES[family] if root+':'+name in lookup)
                primary=(lookup[root+':'+PARENT.get(q,q)],)
                key=(primary,family_indexes,q in PARENT)
            if key not in group_lookup:group_lookup[key]=len(groups);groups.append(key)
            prior_columns.append(group_lookup[key])
        values=[]
        for primary,family,extension in groups:
            value=baseline[:,primary].sum(axis=1)
            if family:
                family_value=baseline[:,family].sum(axis=1)
                value=np.maximum(value,.25*family_value) if extension else np.minimum(1,value+.03*family_value)
            values.append(value)
        priors=np.stack(values,axis=1)
        prior_columns=np.asarray(prior_columns)
        # Derive a silence mask directly from the original audio, not a model guess.
        silent=np.array([np.max(np.abs(pcm[int(t*22050):min(len(pcm),int(t*22050)+512)]),initial=0)<1e-5 for t in times])
        penalties=np.full(count,2.8,dtype=np.float32)
        if beats:
            positions=np.searchsorted(beats,times)
            a=np.asarray(beats)[np.clip(positions,0,len(beats)-1)];b=np.asarray(beats)[np.clip(positions-1,0,len(beats)-1)]
            penalties[np.minimum(np.abs(times-a),np.abs(times-b))<.07]=1.8
        def observations():
            for start in range(0,count,128):
                end=min(count,start+128)
                score=1.2*np.log(np.maximum(priors[baseline_frames[start:end]][:,prior_columns],1e-7))
                for k,head in enumerate(heads):
                    weight=1.0 if k==0 else .65
                    score+=weight*np.log(np.maximum(head[start:end,self.components[:,k]],1e-7))
                for n in range(start,end):
                    row=score[n-start]
                    if silent[n]:row[:]=-1000;row[0]=0
                    yield row
        chosen=sequence_decode(observations(),penalties,check=check)
        bass_frames=np.minimum(np.arange(len(baseline))*4,len(heads[1])-1)
        base_names,base_confidence,base_margins=grouped_candidates(baseline,baseline_labels,heads[1][bass_frames])
        frames=[]
        for t,index in enumerate(chosen):
            label=self.labels[index];support=float(heads[0][t,self.components[index,0]])
            frame=int(baseline_frames[t]);base_score=float(base_confidence[frame]);base_label=base_names[frame]
            base_reliable=base_label not in ('X','N') and base_score>=.35 and base_margins[frame]>=.04
            candidate_quality=label.split('/')[0].split(':')[-1]
            agrees=label!='N' and base_reliable and label.split(':')[0]==base_label.split(':')[0] and PARENT.get(candidate_quality,candidate_quality)==base_label.split(':')[-1]
            if not silent[t] and label!='N':
                # Extensions need positive acoustic support from their output head.
                suffix=self.components[index,2:]
                supported=all(heads[k+2][t,c]>=.35 or (k==0 and agrees) for k,c in enumerate(suffix) if c>0)
                if (support<.20 and not agrees) or not supported:label='X'
            # Preserve a strong, supported baseline decision when the component
            # model is weak. An acoustically supported richer label can enrich
            # a simpler chord of the same root instead of being flattened.
            if not silent[t] and base_reliable:
                known=label not in ('X','N')
                extra=[float(heads[k+2][t,c]) for k,c in enumerate(self.components[index,2:]) if k>0 and c>0]
                enrich=known and label.split(':')[0]==base_label.split(':')[0] and self.components[index,2:].any() and (support>=.55 or (agrees and extra and min(extra)>=.6))
                if label in ('X','N') or (base_score>=.55 and label!=base_label and not enrich):
                    label,support=base_label,base_score
            frames.append({'start':float(times[t]),'end':min(duration,float((t+1)*512/22050)),
                           'chord':'N' if silent[t] else label,'model_score':0.0 if silent[t] else support,'edited':False})
        return stabilize_equivalent_names(frames)
