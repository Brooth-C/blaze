"""Validate six selected Mega heads before publishing any model asset."""
from pathlib import Path
import argparse
import json
import resource
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.roformer import RoformerSeparator
from music_studio.instrument_assets import SELECTED


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    models = json.loads((args.assets / 'models.json').read_text())
    trunk_names = ['front', *[f'block{i}' for i in range(12)]]
    expected = trunk_names + ['head-' + name for name in SELECTED]
    if list(models) != expected or any(meta['file'] != name + '.onnx' for name, meta in models.items()):
        raise ValueError('Unexpected exported instrument layout.')
    reference = np.load(args.assets / 'reference.npz')
    engine = RoformerSeparator()
    engine.directory = args.assets
    features = reference['spec']
    start = time.monotonic()
    for name in trunk_names:
        features = engine._graph(models[name], features, threading.Event())
        print('Verified trunk:', name, flush=True)
    masks = []
    for name in SELECTED:
        masks.append(engine._graph(models['head-' + name], features, threading.Event()))
        print('Verified head:', name, flush=True)
    actual = np.concatenate(masks, axis=1)
    error = actual - reference['mask']
    report = {'max_abs': float(np.abs(error).max()), 'rms': float(np.sqrt(np.mean(error.astype('float64') ** 2))),
              'p999': float(np.percentile(np.abs(error), 99.9)), 'seconds': time.monotonic() - start,
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if not np.isfinite(actual).all() or report['rms'] >= 1e-5 or report['p999'] >= 1e-4:
        raise ValueError('Instrument conversion failed original-source parity: ' + json.dumps(report))
    if sys.platform.startswith('linux') and report['peak_rss_kib'] >= 4 * 1024 ** 2:
        raise ValueError('Instrument inference exceeded the 4 GiB memory gate.')
    (args.assets / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
