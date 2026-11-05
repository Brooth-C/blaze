"""Build-only strict piano subset and original spectral references for MLX."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import torch
import yaml
from safetensors.numpy import save_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools/roformer'))
from export import TupleLoader
from spec_models import SpecOnlyBSRoformer
from music_studio.instrument_assets import CHECKPOINT_SHA, CONFIG_SHA, SOURCE_REVISION
from music_studio.mlx_piano_model import BANDS, validate_weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--msst', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(['git','-C',str(args.msst),'rev-parse','HEAD'], text=True).strip() != SOURCE_REVISION:
        raise ValueError('Use the pinned original architecture source.')
    with args.checkpoint.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != CHECKPOINT_SHA:
            raise ValueError('Original Mega checkpoint checksum mismatch.')
    config_path = ROOT/'tools/instruments/config.yaml'
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != CONFIG_SHA:
        raise ValueError('Original Mega config checksum mismatch.')
    config = yaml.load(config_path.read_text(), Loader=TupleLoader)
    if tuple(config['model']['freqs_per_bands']) != BANDS or config['training']['instruments'][33] != 'piano':
        raise ValueError('Original band or piano-head ordering changed.')
    state = torch.load(args.checkpoint, map_location='cpu', mmap=True, weights_only=True)
    if 'state_dict' in state:state = state['state_dict']
    selected = {}
    for name, tensor in state.items():
        if name.startswith('mask_estimators.'):
            prefix, index, suffix = name.split('.',2)
            if int(index) != 33:continue
            name = f'{prefix}.0.{suffix}'
        selected[name] = tensor
    sys.path.insert(0, str(args.msst))
    from models.bs_roformer.bs_roformer import BSRoformer
    torch.set_num_threads(2)
    model = BSRoformer(**dict(config['model'],num_stems=1)).eval()
    model.load_state_dict(selected, strict=True)
    weights = {key: value.detach().cpu().float().numpy().copy() for key,value in model.state_dict().items()}
    validate_weights(weights)
    if not all(np.isfinite(value).all() for value in weights.values()):
        raise ValueError('Original model contains invalid parameters.')
    args.output.mkdir(parents=True,exist_ok=True)
    path = args.output/'piano-fp32.safetensors'
    save_file(weights,str(path),metadata={'format':'pt'})
    with path.open('rb') as stream:checksum = hashlib.file_digest(stream,'sha256').hexdigest()
    meta = {'file':path.name,'bytes':path.stat().st_size,'sha256':checksum,
            'checkpoint_sha256':CHECKPOINT_SHA,'source_revision':SOURCE_REVISION,
            'original_head':33,'parameters':len(weights),'dtype':'float32'}
    (args.output/'weights.json').write_text(json.dumps(meta,indent=2)+'\n')
    wrapper = SpecOnlyBSRoformer(model)
    reference = {}
    for name,scale in [('normal',.02),('quiet',1e-14),('silence',0.)]:
        source = np.random.default_rng(5333).normal(0,scale,(1,2050,31,2)).astype('float32')
        with torch.inference_mode():mask = wrapper(torch.from_numpy(source)).numpy()
        reference[name+'-input'] = source;reference[name+'-mask'] = mask
    np.savez(args.output/'reference.npz',**reference)
    print(json.dumps(meta),flush=True)


if __name__ == '__main__':main()
