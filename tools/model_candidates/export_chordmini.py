"""Export the pinned BTC CL candidate with strict weights and real-logit parity.

Build-only PyTorch dependency. Does not change installed/default Blaze models.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SOURCE_COMMIT = 'aa6e3a8d7b017f082fd2aaff9329d5c26af49c03'
CHECKPOINT_SHA = 'e0a12ca6d881f81e01dfb459b4836ec7dac8d8f87b0170a412b5807256b3a1fc'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE_COMMIT:
        parser.error('Use the reviewed ChordMini source commit.')
    # Reject source modifications, including untracked importable modules.
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=normal'], text=True).strip():
        parser.error('Use a clean source checkout.')
    checkpoint = source / 'checkpoints/btc_model_best.pth'
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != CHECKPOINT_SHA:
        parser.error('The candidate checkpoint checksum does not match.')
    if args.output.exists():
        parser.error('Choose a new output directory.')
    import numpy as np
    import torch
    import onnxruntime as ort
    import yaml
    torch.set_num_threads(2)
    sys.path.insert(0, str(source))
    from src.models.btc_model import BTC_model
    # No executable pickle globals or upstream strict=False recovery.
    saved = torch.load(checkpoint, map_location='cpu', weights_only=True)
    state = saved.get('model_state_dict', saved.get('model', saved))
    state = {k.removeprefix('module.'): v for k, v in state.items()}
    config = yaml.safe_load((source / 'config/ChordMini.yaml').read_text())['model']
    model = BTC_model(config).eval()
    model.load_state_dict(state, strict=True)
    stats = saved.get('normalization', saved)
    if 'mean' not in stats or 'std' not in stats:
        raise ValueError('Checkpoint normalization must be explicit.')
    mean, std = float(stats['mean']), float(stats['std'])
    if not np.isfinite([mean, std]).all() or std <= 0:
        raise ValueError('Invalid checkpoint normalization.')
    class Logits(torch.nn.Module):
        def __init__(self, network):
            super().__init__()
            self.network = network
        def forward(self, features):
            return self.network(features)
    inference = Logits(model).eval()
    args.output.mkdir(parents=True)
    path = args.output / 'chordmini_btc_cl.onnx'
    torch.onnx.export(inference, torch.zeros(1, 108, 144), str(path),
                      input_names=['features'], output_names=['logits'], opset_version=17, dynamo=False)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
    errors = []
    for scale in (0., 1e-8, .1, 1., 5.):
        features = np.random.default_rng(17).normal(0, scale, (1,108,144)).astype('float32')
        with torch.inference_mode():
            expected = inference(torch.from_numpy(features)).numpy()
        actual = session.run(None, {'features': features})[0]
        error = float(np.max(np.abs(expected-actual)))
        if not np.isfinite(actual).all() or error > .001 or not np.array_equal(expected.argmax(-1), actual.argmax(-1)):
            raise ValueError('ONNX export did not preserve reference logits/labels.')
        errors.append(error)
    qualities = ['min','maj','dim','aug','min6','maj6','min7','minmaj7','maj7','7','dim7','hdim7','sus2','sus4']
    labels = [root+':'+q for root in ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'] for q in qualities]+['X','N']
    stored_labels = saved.get('idx_to_chord')
    if not isinstance(stored_labels, dict) or len(stored_labels) != 170:
        raise ValueError('Checkpoint must contain its complete vocabulary.')
    from src.utils.chords import normalize_enharmonic_label
    for i, label in enumerate(labels):
        actual = stored_labels.get(i, stored_labels.get(str(i)))
        actual = normalize_enharmonic_label(actual)
        if actual not in (label, label.removesuffix(':maj')):
            raise ValueError('Checkpoint vocabulary order differs from the adapter.')
    contract = {'rate':22050,'hop':2048,'bins':144,'bins_per_octave':24,'fmin':'C1',
                'librosa':'0.11.0','log_epsilon':1e-6,'normalization_epsilon':1e-8,
                'window':108,'stride':54,'padding':'raw-feature-zero-before-normalization',
                'aggregation':'logit','smoothing':False,'mean':mean,'std':std,'labels':labels}
    identity = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    manifest = {'schema_version':1,'candidate':'chordmini-btc-cl','experimental':True,
                'source_commit':SOURCE_COMMIT,'checkpoint_sha256':CHECKPOINT_SHA,
                'model':{'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size},
                'frontend_sha256':identity,'contract':contract,'onnx_max_errors':errors,
                'license':'MIT source; checkpoint redistribution not yet approved',
                'versions':{'torch':torch.__version__,'ort':ort.__version__,'numpy':np.__version__}}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.output/'LICENSE-ChordMini.txt').write_bytes((source/'LICENSE').read_bytes())
    print(json.dumps({'artifact':str(path),'parity_max_error':max(errors)}))


if __name__ == '__main__':
    main()
