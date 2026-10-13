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
print('Sequence: transient rejection, sustained/offbeat changes, extension evidence, baseline preservation, silence and cancellation PASS')
