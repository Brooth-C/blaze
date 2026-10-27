"""Export-neutral surgery on the MSST RoFormer models.

Three changes, none of which touch a single weight:

1. `stft` / `istft` are amputated. ONNX has no complex dtype and no `istft`, so
   the graph runs spec-in / mask-out and the driver owns the transform. This is
   the same cut ZFTurbo makes in `MSS_ONNX_TensorRT/models_without_stft`.
2. `Attend.flash` is forced off, so attention traces as explicit
   einsum+softmax instead of `scaled_dot_product_attention`. Same math.
3. `nn.GLU` is replaced by an equivalent slice+sigmoid+mul. `F.glu` exports as
   `Split -> Sigmoid -> Mul`, and the DirectML EP computes that specific
   pattern WRONG (measured: it returns `a * sigmoid(a)`, whose minimum is the
   -0.2785 fingerprint seen in the broken output). Slicing sidesteps it and is
   bit-identical on CPU.
"""
from __future__ import annotations

import torch
from einops import pack, rearrange, unpack
from torch import nn


class SlicedGLU(nn.Module):
    """`nn.GLU(dim=-1)` written with slices instead of a 2-way Split.

    Exists only to dodge a DirectML EP miscomputation of the exported
    `Split -> Sigmoid -> Mul` triple; numerically identical everywhere else.
    """

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        half = x.shape[-1] // 2
        return x[..., :half] * torch.sigmoid(x[..., half:])


def patch_for_export(model: nn.Module) -> dict[str, int]:
    """Apply changes 2 and 3 in place. Returns what was touched, for the manifest."""
    counts = {"flash_disabled": 0, "glu_replaced": 0}
    for module in model.modules():
        if hasattr(module, "flash") and hasattr(module, "attn_dropout"):
            module.flash = False
            counts["flash_disabled"] += 1
    for parent in model.modules():
        for name, child in list(parent.named_children()):
            if isinstance(child, nn.GLU):
                setattr(parent, name, SlicedGLU())
                counts["glu_replaced"] += 1
    return counts


def _axial_transformers(model: nn.Module, x: torch.Tensor) -> torch.Tensor:
    """The depth loop shared by both architectures (no torch.checkpoint, no skip)."""
    for time_transformer, freq_transformer in model.layers:
        x = rearrange(x, "b t f d -> b f t d")
        x, ps = pack([x], "* t d")
        x = time_transformer(x)
        (x,) = unpack(x, ps, "* t d")
        x = rearrange(x, "b f t d -> b t f d")
        x, ps = pack([x], "* f d")
        x = freq_transformer(x)
        (x,) = unpack(x, ps, "* f d")
    return x


class SpecOnlyBSRoformer(nn.Module):
    """spec [b, F*S, T, 2] -> mask [b, N, F*S, T, 2] (complex pairs)."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.m = model

    def forward(self, spec: torch.Tensor) -> torch.Tensor:
        m = self.m
        x = m.band_split(rearrange(spec, "b f t c -> b t (f c)"))
        x = m.final_norm(_axial_transformers(m, x))
        mask = torch.stack([fn(x) for fn in m.mask_estimators], dim=1)
        return rearrange(mask, "b n t (f c) -> b n f t c", c=2)


class SpecOnlyMelBandRoformer(nn.Module):
    """spec [b, F*S, T, 2] -> band-averaged mask [b, N, F*S, T, 2].

    The mel gather table and the overlap-averaging scatter live INSIDE the graph
    (both are constant index ops, and both were measured correct on the DirectML
    EP), so the driver is identical for the two architectures.
    """

    def __init__(self, model: nn.Module):
        super().__init__()
        self.m = model
        self.register_buffer("freq_indices", model.freq_indices.long(), persistent=False)
        denom = model.num_bands_per_freq.float().clamp(min=1e-8)
        denom = denom.repeat_interleave(model.audio_channels)
        self.register_buffer("denom", denom[:, None, None], persistent=False)

    def forward(self, spec: torch.Tensor) -> torch.Tensor:
        m = self.m
        gathered = spec[:, self.freq_indices]  # [b, G, T, 2]
        x = m.band_split(rearrange(gathered, "b f t c -> b t (f c)"))
        x = _axial_transformers(m, x)
        masks = torch.stack([fn(x) for fn in m.mask_estimators], dim=1)
        masks = rearrange(masks, "b n t (f c) -> b n f t c", c=2)
        b, n, _, t, _ = masks.shape
        idx = self.freq_indices[None, None, :, None, None].expand(
            b, n, self.freq_indices.shape[0], t, 2
        )
        summed = torch.zeros(
            b, n, spec.shape[1], t, 2, dtype=masks.dtype, device=masks.device
        ).scatter_add_(2, idx, masks)
        return summed / self.denom
