"""Check the piano-head export against its original Torch computation."""
import argparse
import json
from pathlib import Path
import sys
import threading
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.native_piano_assets import HEAD
from music_studio.roformer import RoformerSeparator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    args = parser.parse_args()
    metadata = json.loads((args.assets / 'models.json').read_text())
    expected = {k: HEAD[k] for k in ('file', 'bytes', 'sha256', 'input_shape', 'output_shape')}
    if metadata != {'head-piano': expected}:
        raise ValueError('Piano export does not match its reviewed pins.')
    reference = np.load(args.assets / 'reference.npz')
    separator = RoformerSeparator()
    separator.directory = args.assets
    start = time.monotonic()
    actual = separator._graph(expected, reference['latent'], threading.Event())
    error = np.abs(actual.astype('float64') - reference['mask'])
    report = {'max_abs': float(error.max()), 'rms': float(np.sqrt(np.mean(error ** 2))),
              'p999': float(np.percentile(error, 99.9)), 'seconds': time.monotonic() - start}
    if not np.isfinite(actual).all() or report['rms'] >= 1e-5 or report['p999'] >= 1e-4:
        raise ValueError('Original piano-head parity failed: ' + json.dumps(report))
    (args.assets / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
