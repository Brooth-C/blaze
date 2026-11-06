"""Export the original Mega53 piano head; reuse the pinned shared trunk.

Build only, with the same pinned dependencies as export.py. No training or
frequency truncation; this is the original complex mask estimator at index33.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import onnx
import torch
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools/roformer'))
from export import TupleLoader
from spec_models import patch_for_export
from music_studio.instrument_assets import CHECKPOINT_SHA, CONFIG_SHA, SOURCE_REVISION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--msst', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', '-C', str(args.msst), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_REVISION:
        raise ValueError('Use the pinned original architecture revision.')
    with args.checkpoint.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != CHECKPOINT_SHA:
            raise ValueError('Original Mega checkpoint checksum mismatch.')
    config_path = Path(__file__).parent / 'config.yaml'
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != CONFIG_SHA:
        raise ValueError('Original Mega config checksum mismatch.')
    config = yaml.load(config_path.read_text(), Loader=TupleLoader)
    if config['training']['instruments'][33] != 'piano':
        raise ValueError('Original piano-head ordering changed.')
    sys.path.insert(0, str(args.msst))
    from models.bs_roformer.bs_roformer import BSRoformer
    # Import the existing head wrapper without executing its command entrypoint.
    import importlib.util
    spec = importlib.util.spec_from_file_location('mega_export', Path(__file__).parent / 'export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    torch.set_num_threads(2)
    state = torch.load(args.checkpoint, map_location='cpu', weights_only=True, mmap=True)
    if 'state_dict' in state:
        state = state['state_dict']
    selected = {}
    for name, tensor in state.items():
        if name.startswith('mask_estimators.'):
            prefix, index, suffix = name.split('.', 2)
            if int(index) != 33:
                continue
            name = f'{prefix}.0.{suffix}'
        selected[name] = tensor
    model = BSRoformer(**dict(config['model'], num_stems=1)).eval()
    model.load_state_dict(selected, strict=True)
    del state, selected
    gc.collect()
    head = module.Head(model, 0).eval()
    latent = torch.from_numpy(np.random.default_rng(5333).normal(0, .1, (1, 1723, 62, 256)).astype('float32'))
    start = time.monotonic()
    with torch.inference_mode():
        reference = head(latent).numpy()
    patch_for_export(head)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / 'head-piano.onnx'
    with torch.inference_mode():
        torch.onnx.export(head, (latent,), str(path), opset_version=17, do_constant_folding=True,
                          input_names=['x'], output_names=['y'], dynamo=False)
    graph = onnx.load(path)
    shape = graph.graph.output[0].type.tensor_type.shape
    del shape.dim[:]
    for size in reference.shape:
        shape.dim.add().dim_value = int(size)
    onnx.checker.check_model(graph)
    onnx.save(graph, path)
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = {'file': path.name, 'bytes': path.stat().st_size, 'sha256': checksum,
                'input_shape': list(latent.shape), 'output_shape': list(reference.shape)}
    (args.output / 'models.json').write_text(json.dumps({'head-piano': metadata}, indent=2) + '\n')
    (args.output / 'export.json').write_text(json.dumps({
        'checkpoint_sha256': CHECKPOINT_SHA, 'source_revision': revision,
        'config_sha256': CONFIG_SHA, 'original_head': 33, 'instrument': 'piano',
        'segment_samples': 882000, 'models': {'head-piano': metadata}}, indent=2) + '\n')
    np.savez(args.output / 'reference.npz', latent=latent.numpy(), mask=reference)
    print(json.dumps({'model': metadata, 'seconds': time.monotonic() - start}), flush=True)


if __name__ == '__main__':
    main()
