"""Export the verified MIT Music X Lab five-model ensemble; no training."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,tomllib
import numpy as np,torch,onnxruntime as ort
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
SOURCE_COMMIT='d8ab9ac99bce081bb79065d717f96e2c3b2099c8'
git=['git','-c','safe.directory='+a.source.resolve().as_posix(),'-C',str(a.source)]
if subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip()!=SOURCE_COMMIT:
    raise ValueError('Use the pinned, reviewed LV source revision.')
subprocess.run(git+['diff','--exit-code'],check=True,stdout=subprocess.DEVNULL)
sys.path.insert(0,str(a.source.resolve()))
from lv_chordia.chordnet_ismir_naive import ChordNet
from lv_chordia.complex_chord import Chord
torch.set_num_threads(2);a.output.mkdir(parents=True,exist_ok=True)
assets=tomllib.loads((a.source/'lv_chordia/config/checkpoints.toml').read_text())['models']['lv_chordia']['artifacts']
exported=[]
for n,asset in enumerate(assets):
    checkpoint=a.source/'weights'/asset['name']
    digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if digest!=asset['sha256']:raise ValueError('Published checkpoint digest mismatch.')
    model=ChordNet(None,use_gpu=False).eval()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True)['net'])
    target=a.output/f'lv_chord_{n}.onnx';names=['triad','bass','seventh','ninth','eleventh','thirteenth']
    axes={'features':{1:'frames'},**{name:{0:'frames'} for name in names}}
    torch.onnx.export(model,torch.rand(1,430,252),str(target),opset_version=17,input_names=['features'],output_names=names,dynamic_axes=axes,dynamo=False)
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    session=ort.InferenceSession(target.read_bytes(),sess_options=options,providers=['CPUExecutionProvider'])
    for length in (180,430):
        features=np.random.default_rng(length).uniform(0,30,(1,length,252)).astype(np.float32)
        with torch.inference_mode():reference=[v.numpy() for v in model(torch.from_numpy(features))]
        actual=session.run(None,{'features':features})
        error=max(float(np.max(np.abs(x-y))) for x,y in zip(reference,actual))
        if error>.002:raise ValueError(f'Structured ONNX parity failed: {error}')
    exported.append({'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'checkpoint_sha256':digest})
    print('Ensemble export/parity PASS',n,error,flush=True)
templates=(a.source/'lv_chordia/data/extended_chord_list.txt').read_text().splitlines()
templates+=['C:minmaj7','C:min11','C:maj13','C:min13']
labels=[]
# Store component indices, converting relative slash bass into note names.
qualities={line.split(':')[1].split('/')[0] for line in templates if line.startswith('C:')}
for root in range(12):
    for quality in sorted(qualities):
        if quality=='sus4(b7)':quality='7sus4';source_quality='sus4(b7)'
        else:source_quality=quality
        label_root=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][root]
        component=Chord(label_root+':'+source_quality).to_numpy().tolist()
        labels.append({'label':label_root+':'+quality,'components':component})
        for degree in ('b3','3','5','b7'):
            try:
                arr=Chord(label_root+':'+source_quality+'/'+degree).to_numpy().tolist()
            except (ValueError,Exception):continue
            # Every component's bass field is an absolute pitch number.
            if arr[1]>=0 and arr[1]!=root:
                bass=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][arr[1]]
                labels.append({'label':label_root+':'+quality+'/'+bass,'components':arr})
labels=[{'label':'N','components':[0,-1,0,0,0,0]}]+labels
labels=list({item['label']:item for item in labels}.values())
version=subprocess.check_output(['git','-c','safe.directory='+a.source.resolve().as_posix(),'-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
manifest={'schema_version':1,'name':'Music X Lab structured ensemble','license':'MIT','source':'https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition','export_source':'https://github.com/openmirlab/lv-chordia','version':version,'sample_rate':22050,'hop_length':512,'feature_size':252,'models':exported,'labels':labels}
frontend=a.output/'lv_cqt.npz'
if not frontend.is_file():raise ValueError('Build the portable LV frontend first.')
manifest['frontend']={'file':frontend.name,'sha256':hashlib.sha256(frontend.read_bytes()).hexdigest(),'reference':'librosa 0.10.2.post1 hybrid CQT / auto tuning / Soxr HQ'}
(a.output/'structured_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
shutil.copy2(a.source/'LICENSE',a.output/'LICENSE-MusicXLab.txt')
print('Structured vocabulary',len(labels),'labels; verified MIT weights exported.',flush=True)
