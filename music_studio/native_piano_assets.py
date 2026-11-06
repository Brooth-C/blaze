"""Original Mega53 acoustic-piano head; shared trunk remains independently pinned."""
from .instrument_assets import CHECKPOINT_SHA, SOURCE_REVISION, WEIGHT_LICENSE

ORIGINAL_HEAD = 33
HEAD = {
    'file': 'head-piano.onnx', 'bytes': 49684302,
    'sha256': '13a02c35968a6d8cd56ea4384f706b976cfa3d952b5e48ef3d502e6061ae1697',
    'input_shape': [1, 1723, 62, 256], 'output_shape': [1, 1, 2050, 1723, 2],
}


def manifest():
    return {'head': HEAD, 'license': 'MIT', 'checkpoint_sha256': CHECKPOINT_SHA,
            'source_revision': SOURCE_REVISION, 'weight_license_evidence': WEIGHT_LICENSE,
            'instrument': 'piano', 'original_head': ORIGINAL_HEAD,
            'sample_rate': 44100, 'segment_samples': 882000}
