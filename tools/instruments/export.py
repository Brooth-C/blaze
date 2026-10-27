"""Export only requested independent heads from the MIT Mega 53 checkpoint.

Same pinned CPU build dependencies as tools/roformer/export.py. The original
53-head architecture shares a trunk and has independent mask estimators; select
six estimators without training, quantization or changing their parameters.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import MethodType

import numpy as np
import torch
import yaml
from einops import rearrange

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools/roformer'))
from export import Front, Block, bounded_attention, TupleLoader
from spec_models import SpecOnlyBSRoformer, patch_for_export
from music_studio.instrument_assets import CHECKPOINT_SHA, CONFIG_SHA, SOURCE_REVISION, ORIGINAL_HEADS, SELECTED


class Head(torch.nn.Module):
    def __init__(self, model, index):
        super().__init__()
        self.norm, self.head = model.final_norm, model.mask_estimators[index]

    def forward(self, x):
        mask = self.head(self.norm(x))[:, None]
        return rearrange(mask, 'b n t (f c) -> b n f t c', c=2)


def subset_state(state):
    result = {}
    mapping = {source: target for target, source in enumerate(ORIGINAL_HEADS)}
    for name, tensor in state.items():
        if name.startswith('mask_estimators.'):
            prefix, index, suffix = name.split('.', 2)
            if int(index) not in mapping:
                continue
            name = f'{prefix}.{mapping[int(index)]}.{suffix}'
        result[name] = tensor
    return result


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
    if tuple(config['training']['instruments'][i] for i in ORIGINAL_HEADS) != SELECTED:
        raise ValueError('Original instrument-head ordering changed.')
    sys.path.insert(0, str(args.msst))
    from models.bs_roformer.bs_roformer import BSRoformer
    torch.set_num_threads(2)
    state = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    if isinstance(state, dict) and 'state_dict' in state:
        state = state['state_dict']
    selected = subset_state(state)
    del state
    gc.collect()
    kwargs = dict(config['model'], num_stems=len(SELECTED))
    model = BSRoformer(**kwargs).eval()
    model.load_state_dict(selected, strict=True)
    del selected
    gc.collect()
    print('Loaded exact selected heads, parameters:', sum(p.numel() for p in model.parameters()), flush=True)
    segment = int(config['inference']['chunk_size'])
    assert segment == 882000 and kwargs['stft_hop_length'] == 512
    audio = torch.from_numpy(np.random.default_rng(53).normal(0, .02, (1, 2, segment)).astype('float32'))
    spec = torch.stft(audio.reshape(2, -1), n_fft=2048, hop_length=512,
                      window=torch.hann_window(2048), return_complex=True)
    spec = torch.view_as_real(spec).permute(1, 0, 2, 3).reshape(1, 2050, 1723, 2).contiguous()
    wrapper = SpecOnlyBSRoformer(model).eval()
    start = time.monotonic()
    with torch.inference_mode():
        reference = wrapper(spec).numpy()
    print('Original selected-head inference seconds:', time.monotonic() - start, flush=True)
    patch_for_export(model)
    for module in model.modules():
        if hasattr(module, 'attn_dropout') and hasattr(module, 'flash'):
            module.forward = MethodType(bounded_attention, module)
    args.output.mkdir(parents=True, exist_ok=True)
    np.savez(args.output / 'reference.npz', spec=spec.numpy(), mask=reference)
    stages = [('front', Front(model)), *[(f'block{i}', Block(layer)) for i, layer in enumerate(model.layers)],
              *[(f'head-{name}', Head(model, i)) for i, name in enumerate(SELECTED)]]
    import onnx
    x, trunk, masks, models = spec, None, [], {}
    for name, stage in stages:
        stage.eval()
        if name.startswith('head-'):
            if trunk is None:
                trunk = x
            x = trunk
        start = time.monotonic()
        path = args.output / (name + '.onnx')
        input_shape = list(x.shape)
        with torch.inference_mode():
            y = stage(x)
            torch.onnx.export(stage, (x,), str(path), opset_version=17, do_constant_folding=True,
                              input_names=['x'], output_names=['y'], dynamo=False)
        graph = onnx.load(path)
        shape = graph.graph.output[0].type.tensor_type.shape
        del shape.dim[:]
        for size in y.shape:
            shape.dim.add().dim_value = int(size)
        onnx.checker.check_model(graph)
        onnx.save(graph, path)
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        models[name] = {'file': path.name, 'bytes': path.stat().st_size, 'sha256': checksum,
                        'input_shape': input_shape, 'output_shape': list(y.shape)}
        if name.startswith('head-'):
            masks.append(y.numpy())
        else:
            x = y
        print('Exported', name, path.stat().st_size, 'seconds', time.monotonic() - start, flush=True)
    actual = np.concatenate(masks, axis=1)
    parity = float(np.max(np.abs(actual - reference)))
    if parity >= 1e-4:
        raise ValueError('Selected-head export failed original-source parity: ' + str(parity))
    report = {'checkpoint_sha256': CHECKPOINT_SHA, 'source_revision': revision, 'config_sha256': CONFIG_SHA,
              'original_heads': list(ORIGINAL_HEADS), 'selected': list(SELECTED),
              'segment_samples': segment, 'rewrite_max_abs': parity, 'models': models}
    (args.output / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
    (args.output / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Selected-head rewrite parity:', parity, flush=True)


if __name__ == '__main__':
    main()
