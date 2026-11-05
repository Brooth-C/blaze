"""Strict, FP32 original piano subset for the optional Metal execution path."""
from .instrument_assets import CHECKPOINT_SHA, SOURCE_REVISION, WEIGHT_LICENSE

WEIGHTS = {'file': 'piano-fp32.safetensors', 'bytes': 154847584,
           'sha256': 'ab79a7c00899949975e7090abb16b6702c32f0bcc22df6fd459004e125bf4160'}


def manifest():
    return {'weights': WEIGHTS, 'checkpoint_sha256': CHECKPOINT_SHA,
            'source_revision': SOURCE_REVISION, 'original_head': 33,
            'parameters': 699, 'dtype': 'float32', 'license': 'MIT',
            'weight_license_evidence': WEIGHT_LICENSE}
