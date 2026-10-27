"""Gate exported sequential graphs against the captured original Torch masks."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    models = json.loads((args.assets / 'models.json').read_text())
    expected = ['front', *[f'block{i}' for i in range(8)], 'heads']
    if list(models) != expected or any(meta['file'] != name + '.onnx' for name, meta in models.items()):
        raise ValueError('Unexpected exported model layout.')
    reference = np.load(args.assets / 'reference.npz')
    engine = RoformerSeparator()
    engine.directory = args.assets
    features = reference['spec']
    start = time.monotonic()
    for name, meta in models.items():
        features = engine._graph(meta, features, threading.Event())
        print('Verified block:', name, flush=True)
    error = features - reference['mask']
    report = {'max_abs': float(np.abs(error).max()),
              'rms': float(np.sqrt(np.mean(error.astype('float64') ** 2))),
              'p999': float(np.percentile(np.abs(error), 99.9)),
              'seconds': time.monotonic() - start,
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    if not np.isfinite(features).all() or report['rms'] >= 1e-5 or report['p999'] >= 1e-4:
        raise ValueError('ONNX conversion failed original-model parity: ' + json.dumps(report))
    if sys.platform.startswith('linux') and report['peak_rss_kib'] >= 4 * 1024 ** 2:
        raise ValueError('Sequential inference exceeded the 4 GiB memory gate.')
    (args.assets / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
