"""Sequence and structured-ensemble acoustic safeguards."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from music_studio.structured import sequence_decode,StructuredRecognizer

scores=np.tile([0.,-4.],(40,1));scores[20]=[-.9,0]
assert np.all(sequence_decode(scores,np.full(40,2.8))==0)
scores[22:]=[-6,0]
assert np.all(sequence_decode(scores,np.full(40,2.8))[22:]==1)
# A strong change can occur away from a beat; the rhythm prior is soft.
assert sequence_decode(np.array([[0.,-10.],[-10.,0.]]),np.full(2,2.8)).tolist()==[0,1]
assert sequence_decode([],[]).size==0
try:sequence_decode(scores,np.full(40,2.8),check=lambda:(_ for _ in ()).throw(RuntimeError('cancel')))
except RuntimeError:pass
else:raise AssertionError('Cancellation was ignored')

recognizer=object.__new__(StructuredRecognizer)
recognizer.labels=['N','C:maj','C:7','C:9']
recognizer.components=np.array([[0,0,0,0,0,0],[1,1,0,0,0,0],[1,1,2,0,0,0],[1,1,2,1,0,0]])
count=40;duration=count*512/22050
heads=[np.tile(row,(count,1)).astype(np.float32) for row in [
 [.01,.99]+[0.]*71,[.01,.99]+[0.]*11,[.01,.01,.97,.01],[.01,.97,.01,.01],[.98,.01,.01],[.98,.01,.01]]]
base=np.tile([.02,.95,.02,.01],(10,1)).astype(np.float32)
labels=['C:maj','C:7','N','X'];audio=np.ones(count*512,dtype=np.float32)*.1
frames=recognizer.decode(heads,base,labels,duration,[],audio)
assert all(f['chord']=='C:9' for f in frames)
heads[3][:]=np.array([.97,.01,.01,.01])
frames=recognizer.decode(heads,base,labels,duration,[],audio)
assert all(f['chord']=='C:7' for f in frames)
frames=recognizer.decode(heads,base,labels,duration,[],audio*0)
assert all(f['chord']=='N' for f in frames)
assert abs(frames[-1]['end']-duration)<1e-8
assert all(abs(a['end']-b['start'])<1e-8 for a,b in zip(frames,frames[1:]))

# Frozen pre-optimization decoder: preserve the entire path, including ties,
# short vocabularies and both production floating-point input precisions.
def reference_sequence_decode(emissions,penalties,beam=20,check=lambda:None):
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

rng=np.random.default_rng(862)
for dtype in (np.float32,np.float64):
    for vocabulary in (2,25,170,1000):
        for beam in (1,20):
            for ties in (False,True):
                emissions=rng.normal(size=(300,vocabulary)).astype(dtype)
                if ties:emissions=np.round(emissions)
                penalties=rng.uniform(0,5,300).astype(dtype)
                np.testing.assert_array_equal(sequence_decode(emissions,penalties,beam),
                                              reference_sequence_decode(emissions,penalties,beam))
np.testing.assert_array_equal(sequence_decode(np.zeros((300,25)),np.zeros(300)),
                              reference_sequence_decode(np.zeros((300,25)),np.zeros(300)))

print('Sequence: transient rejection, sustained/offbeat changes, extension evidence, baseline preservation, silence and cancellation PASS')
