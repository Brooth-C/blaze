"""Original spectral-mask parity for the strict MLX piano evaluator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from music_studio.mlx_piano_assets import WEIGHTS
from music_studio.mlx_piano_model import PianoModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu','gpu'], required=True)
    args = parser.parse_args()
    path = args.assets/WEIGHTS['file']
    with path.open('rb') as stream:checksum = hashlib.file_digest(stream,'sha256').hexdigest()
    if path.stat().st_size != WEIGHTS['bytes'] or checksum != WEIGHTS['sha256']:
        raise ValueError('MLX piano export does not match its reviewed pin.')
    reference = np.load(args.assets/'reference.npz')
    model = PianoModel(path, require_gpu=args.device == 'gpu')
    report = {'device_requested': args.device, 'weights_sha256': checksum, 'cases': []}
    try:
        for name in ['normal','quiet','silence']:
            start = time.monotonic()
            actual = model.predict(reference[name+'-input'])
            error = np.abs(actual.astype('float64')-reference[name+'-mask'])
            case = {'case': name, 'seconds': time.monotonic()-start, 'rms': float(np.sqrt(np.mean(error**2))),
                    'p999': float(np.percentile(error,99.9)), 'max_abs': float(error.max())}
            report['cases'].append(case)
            print(json.dumps(case),flush=True)
            if not np.isfinite(actual).all() or case['rms'] >= 1e-5 or case['p999'] >= 1e-4:
                raise ValueError('MLX piano failed original-model parity.')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        model.close()
        (args.assets/('validation-mlx-'+args.device+'.json')).write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':main()
