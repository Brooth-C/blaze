"""Export pinned pretrained BTC models; no training. Run in a private build venv."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys
import numpy as np
import torch
import yaml
import onnxruntime as ort

COMMIT='2682317be668032e6e4b269ded36adaa2ad57df0'
p=argparse.ArgumentParser()
p.add_argument('--work',required=True,type=Path)
p.add_argument('--output',required=True,type=Path)
p.add_argument('--android-assets',type=Path)
p.add_argument('--source',type=Path)
p.add_argument('--legacy-librosa',required=True,type=Path)
a=p.parse_args()
a.work.mkdir(parents=True,exist_ok=True)
source=a.source or a.work/'BTC-ISMIR19'
if not source.exists():
    subprocess.run(['git','clone','https://github.com/jayg996/BTC-ISMIR19',str(source)],check=True)
    subprocess.run(['git','-C',str(source),'checkout','--detach',COMMIT],check=True)
head=subprocess.check_output(['git','-c','safe.directory='+source.resolve().as_posix(),'-C',str(source),'rev-parse','HEAD'],text=True).strip()
if head!=COMMIT:raise RuntimeError('The model source must match the pinned commit.')
os.environ['BLAZE_LEGACY_LIBROSA']=str(a.legacy_librosa.resolve())
from music_cqt import CQT, librosa
sys.path.insert(0,str(source.resolve()))
from btc_model import BTC_model
np.float=float
torch.set_num_threads(2)
a.output.mkdir(parents=True,exist_ok=True)
class Inference(torch.nn.Module):
    def __init__(self,model):super().__init__();self.model=model
    def forward(self,features):
        hidden,_=self.model.self_attn_layers(features)
        return self.model.output_layer.output_projection(hidden)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'schema_version':1,'source':'https://github.com/jayg996/BTC-ISMIR19','source_commit':COMMIT,'license':'MIT','sample_rate':22050,'chunk_samples':220500,'timestep':108,'feature_size':144,'hop_length':2048,'fmin':32.70319566257483,'bins_per_octave':24,'preprocessing_reference':'librosa 0.6.3 CQT / kaiser_fast','models':{}}
config=yaml.safe_load((source/'run_config.yaml').read_text(encoding='utf-8'))['model']
roots=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
qualities=['min','maj','dim','aug','min6','maj6','min7','minmaj7','maj7','7','dim7','hdim7','sus2','sus4']
rng=np.random.default_rng(7)
allowed=[np.dtype,np.core.multiarray.scalar,type(np.dtype(np.float64)),type(np.dtype(np.float32)),np.ndarray,np.core.multiarray._reconstruct]
for filename,classes,name,expected in [('btc_model.pt',25,'major_minor','71c2c5db17e8c43b8a9a9da5db36ef2d667158c07a214eba16344c154c00bf54'),('btc_model_large_voca.pt',170,'extended','1673d23f8f9a55ae7f9e8b80a51da616debb22675b8d8b67ea6ce0ef37b0ab51')]:
    original=source/'test'/filename
    if digest(original)!=expected:raise RuntimeError('Pretrained checkpoint checksum mismatch.')
    with torch.serialization.safe_globals(allowed):checkpoint=torch.load(original,map_location='cpu',weights_only=True)
    params=dict(config);params['num_chords']=classes
    model=BTC_model(params);model.load_state_dict(checkpoint['model'],strict=True)
    inference=Inference(model.eval()).eval()
    path=a.output/f'btc_{classes}.onnx'
    torch.onnx.export(inference,torch.zeros(1,108,144),str(path),input_names=['features'],output_names=['logits'],opset_version=17,dynamo=False)
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    for _ in range(4):
        features=rng.normal(size=(1,108,144)).astype(np.float32)
        with torch.inference_mode():reference=inference(torch.from_numpy(features)).numpy()
        actual=session.run(None,{'features':features})[0]
        if not np.array_equal(reference.argmax(-1),actual.argmax(-1)) or np.max(abs(reference-actual))>.001:raise RuntimeError('Model export parity failed.')
    labels=[root+':'+quality for root in roots for quality in ['maj','min']]+['N'] if classes==25 else [root+':'+quality for root in roots for quality in qualities]+['X','N']
    manifest['models'][name]={'name':f'BTC-{classes}','version':'ISMIR19','file':path.name,'classes':classes,'sha256':digest(path),'bytes':path.stat().st_size,'source_checkpoint_sha256':expected,'mean':float(checkpoint['mean']),'std':float(checkpoint['std']),'labels':labels,'calibrated_confidence':False}
frontend=CQT().eval();path=a.output/'cqt.onnx'
torch.onnx.export(frontend,torch.zeros(1,220500),str(path),input_names=['pcm'],output_names=['log_cqt'],dynamic_axes={'pcm':{1:'samples'},'log_cqt':{1:'frames'}},opset_version=17,dynamo=False)
options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
for length in [220500,22050,4410]:
    samples=rng.normal(0,.1,length).astype(np.float32)
    reference=np.log(abs(librosa.cqt(samples,sr=22050,n_bins=144,bins_per_octave=24,hop_length=2048))+1e-6).T
    actual=session.run(None,{'pcm':samples[None]})[0][0]
    if actual.shape!=reference.shape or np.max(abs(actual-reference))>.002:raise RuntimeError('CQT export parity failed.')
manifest['frontend']={'file':'cqt.onnx','sha256':digest(path),'bytes':path.stat().st_size,'input':'pcm','output':'log_cqt','input_dtype':'float32','output_dtype':'float64'}
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(a.output/'LICENSE-BTC.txt').write_text((source/'LICENSE').read_text(encoding='utf-8'),encoding='utf-8')
if a.android_assets:
    import shutil
    a.android_assets.mkdir(parents=True,exist_ok=True)
    for name in ['btc_25.onnx','btc_170.onnx','cqt.onnx','manifest.json','LICENSE-BTC.txt']:shutil.copy2(a.output/name,a.android_assets/name)
print('Pretrained exports and parity checks passed. No model was trained.')
