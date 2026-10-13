import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.engine import bridge_uncertain_frames

def frames(labels, widths):
    t=0; output=[]
    for label, width in zip(labels,widths):
        output.append(dict(start=t,end=t+width,chord=label,model_score=.6));t+=width
    return output
f=frames(['C:maj7','X','C:maj7'],[.4,.18,.4]);bridge_uncertain_frames(f)
assert f[1]['chord']=='C:maj7' and f[1]['model_score'] is None
for labels,widths in [(['C:maj7','X','G:7'],[.4,.18,.4]),(['C:maj7','X','C:maj7'],[.4,.5,.4]),(['C:maj7','N','C:maj7'],[.4,.18,.4]),(['X','C:maj7'],[.18,.4]),(['C:maj7','X'],[.4,.18]),(['C:maj7','X','C:maj7'],[.09,.18,.09])]:
    f=frames(labels,widths);bridge_uncertain_frames(f);assert [e['chord'] for e in f]==labels
print('Uncertainty: stable short gap bridged; different chords, silence, long gaps and unstable boundaries preserved PASS')
