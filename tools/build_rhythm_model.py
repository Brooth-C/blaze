"""Export official pretrained Beat This weights. Build-only torch/torchaudio."""
from pathlib import Path
import argparse, hashlib, inspect, json, shutil, subprocess, sys
import numpy as np
import torch
import torchaudio
import onnxruntime as ort

p=argparse.ArgumentParser()
p.add_argument('--source',required=True,type=Path)
p.add_argument('--checkpoint',required=True,type=Path)
p.add_argument('--output',required=True,type=Path)
a=p.parse_args()
SOURCE_COMMIT='b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c'
CHECKPOINT_SHA='8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'
git=['git','-c','safe.directory='+a.source.resolve().as_posix(),'-C',str(a.source)]
if subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()!=SOURCE_COMMIT:
    raise ValueError('Use the pinned, reviewed Beat This source revision.')
subprocess.run(git+['diff','--exit-code'],check=True,stdout=subprocess.DEVNULL)
if hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()!=CHECKPOINT_SHA:
    raise ValueError('Use the verified official final0 checkpoint.')
sys.path.insert(0,str(a.source.resolve()))
from beat_this.model.beat_tracker import BeatThis
torch.set_num_threads(2)
checkpoint=torch.load(a.checkpoint,map_location='cpu',weights_only=True)
config={k:v for k,v in checkpoint['hyper_parameters'].items() if k in inspect.signature(BeatThis).parameters}
model=BeatThis(**config).eval()
model.load_state_dict({k.removeprefix('model.'):v for k,v in checkpoint['state_dict'].items()})
class Outputs(torch.nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,spect):
        value=self.model(spect)
        return value['beat'],value['downbeat']
wrapper=Outputs(model).eval()
a.output.mkdir(parents=True,exist_ok=True)
target=a.output/'beat_this.onnx'
sample=torch.rand(1,1500,128)*7
torch.onnx.export(wrapper,sample,str(target),opset_version=17,input_names=['spect'],output_names=['beat','downbeat'],dynamic_axes={'spect':{1:'frames'},'beat':{1:'frames'},'downbeat':{1:'frames'}},dynamo=False)
options=ort.SessionOptions();options.intra_op_num_threads=2
session=ort.InferenceSession(target.read_bytes(),sess_options=options,providers=['CPUExecutionProvider'])
for length in (220,1500):
    sample=torch.rand(1,length,128)*7
    with torch.inference_mode():reference=[v.numpy() for v in wrapper(sample)]
    actual=session.run(None,{'spect':sample.numpy()})
    error=max(float(np.max(np.abs(x-y))) for x,y in zip(reference,actual))
    if error>.002:raise RuntimeError(f'Rhythm ONNX parity failed: {error}')
    print('ONNX parity',length,error,flush=True)
frontend=torchaudio.transforms.MelSpectrogram(sample_rate=22050,n_fft=1024,hop_length=441,f_min=30,f_max=11000,n_mels=128,mel_scale='slaney',normalized='frame_length',power=1)
np.savez(a.output/'beat_mel.npz',window=frontend.spectrogram.window.numpy(),filter=frontend.mel_scale.fb.numpy())
shutil.copy2(a.source/'LICENSE',a.output/'LICENSE-BeatThis.txt')
version=subprocess.check_output(['git','-c','safe.directory='+str(a.source.resolve()).replace('\\','/'),'-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
def asset(path):return {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
manifest={'schema_version':1,'name':'Beat This! final0','source':'https://github.com/CPJKU/beat_this','version':version,'license':'MIT','checkpoint_sha256':hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),'sample_rate':22050,'hop_length':441,'n_fft':1024,'fps':50,'chunk_frames':1500,'border_frames':6,'network':asset(target),'frontend':asset(a.output/'beat_mel.npz')}
(a.output/'rhythm_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Exported pretrained offline rhythm model',target.stat().st_size,flush=True)
