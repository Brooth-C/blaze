"""Reproduce Blaze's FP32 ONNX graph from reviewed, local source/checkpoint.

Build-only requirements: torch 2.5.1, numpy 1.26.4, onnx 1.17.0, einops 0.8.2,
rotary-embedding-torch 0.8.9, beartype 0.18.5, PyYAML 6.0.2, librosa 0.11.0.
No network access or training-code dependencies are used by the packaged app.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import MethodType
from typing import List

import numpy as np
import torch
import yaml
from einops import rearrange, pack, unpack

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.roformer_assets import CHECKPOINT_SHA, SOURCE_REVISION
from spec_models import SpecOnlyBSRoformer, patch_for_export


class TupleLoader(yaml.SafeLoader):
    pass


TupleLoader.add_constructor('tag:yaml.org,2002:python/tuple',
                            lambda loader, node: tuple(loader.construct_sequence(node)))


@torch.jit.script
def looped_attention(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor, scale: float) -> torch.Tensor:
    """Slice independent batch items; never truncate the key/query context."""
    blocks = torch.jit.annotate(List[torch.Tensor], [])
    for offset in range(0, q.size(0), 4):
        a, b, c = q[offset:offset + 4], k[offset:offset + 4], v[offset:offset + 4]
        probabilities = torch.softmax(torch.matmul(a, b.transpose(-2, -1)) * scale, dim=-1)
        blocks.append(torch.matmul(probabilities, c))
    return torch.cat(blocks, dim=0)


def bounded_attention(self, q, k, v):
    return looped_attention(q, k, v, float(self.scale) if self.scale is not None else .125)


class Front(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.band_split = model.band_split

    def forward(self, x):
        return self.band_split(rearrange(x, 'b f t c -> b t (f c)'))


class Block(torch.nn.Module):
    def __init__(self, layers):
        super().__init__()
        self.time, self.freq = layers[0], layers[1]

    def forward(self, x):
        x = rearrange(x, 'b t f d -> b f t d')
        x, ps = pack([x], '* t d')
        x = self.time(x)
        (x,) = unpack(x, ps, '* t d')
        x = rearrange(x, 'b f t d -> b t f d')
        x, ps = pack([x], '* f d')
        x = self.freq(x)
        (x,) = unpack(x, ps, '* f d')
        return x


class Heads(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.norm, self.heads = model.final_norm, model.mask_estimators

    def forward(self, x):
        x = self.norm(x)
        masks = torch.stack([head(x) for head in self.heads], dim=1)
        return rearrange(masks, 'b n t (f c) -> b n f t c', c=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--msst', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', '-C', str(args.msst), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != SOURCE_REVISION:
        raise ValueError('Use the pinned MSST source revision: ' + SOURCE_REVISION)
    with args.checkpoint.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != CHECKPOINT_SHA:
            raise ValueError('Original checkpoint checksum mismatch.')
    sys.path.insert(0, str(args.msst))
    from models.bs_roformer.bs_roformer import BSRoformer
    config = yaml.load((Path(__file__).parent / 'config.yaml').read_text(), Loader=TupleLoader)
    torch.set_num_threads(2)
    model = BSRoformer(**config['model']).eval()
    model.load_state_dict(torch.load(args.checkpoint, map_location='cpu', weights_only=True))
    wrapper = SpecOnlyBSRoformer(model).eval()
    audio = torch.from_numpy(np.random.default_rng(41).normal(0, .02, (1, 2, 485100)).astype('float32'))
    spec = torch.stft(audio.reshape(2, -1), n_fft=2048, hop_length=441,
                      window=torch.hann_window(2048), return_complex=True)
    spec = torch.view_as_real(spec).permute(1, 0, 2, 3).reshape(1, 2050, 1101, 2).contiguous()
    with torch.inference_mode():
        reference = wrapper(spec).numpy()
    patch_for_export(model)
    for module in model.modules():
        if hasattr(module, 'attn_dropout') and hasattr(module, 'flash'):
            module.forward = MethodType(bounded_attention, module)
    args.output.mkdir(parents=True, exist_ok=True)
    np.savez(args.output / 'reference.npz', spec=spec.numpy(), mask=reference, audio=audio.numpy())
    start = time.monotonic()
    import onnx
    x, models = spec, {}
    stages = [('front', Front(model)), *[(f'block{i}', Block(layer)) for i, layer in enumerate(model.layers)], ('heads', Heads(model))]
    for name, stage in stages:
        stage.eval()
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
        x = y
    parity = float(np.max(np.abs(x.numpy() - reference)))
    if parity >= 1e-4:
        raise ValueError('Block export failed reference parity: ' + str(parity))
    (args.output / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
    report = {'models': models, 'source_revision': revision,
              'checkpoint_sha256': CHECKPOINT_SHA, 'torch_version': torch.__version__,
              'attention_rewrite_max_abs': parity, 'export_seconds': time.monotonic() - start}
    (args.output / 'export.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
