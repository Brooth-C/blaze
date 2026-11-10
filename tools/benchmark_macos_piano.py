"""Compare the released and current piano evaluators on the same Metal device."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from music_studio.mlx_piano_assets import WEIGHTS
from music_studio.mlx_piano_model import PianoModel

BASELINE = '7b4fd9dab1e1b1ab31a90eb7ca76b2ae98fa9c79'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != 'darwin' or platform.machine().lower() != 'arm64'
            or platform.mac_ver()[0].split('.')[0] != '26'):
        parser.error('Run the Metal comparison on macOS 26 Apple Silicon.')
    import mlx.core as mx
    if not mx.metal.is_available():
        parser.error('This comparison requires a real Metal execution device.')
    path = args.assets/WEIGHTS['file']
    with path.open('rb') as stream:
        if path.stat().st_size != WEIGHTS['bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != WEIGHTS['sha256']:
            raise ValueError('Use the reviewed original FP32 weights.')
    # Execute only this fixed, reviewed release's evaluator, never a supplied ref.
    original = subprocess.check_output(['git', 'show', BASELINE+':music_studio/mlx_piano_model.py'], cwd=ROOT, text=True)
    namespace = {}
    exec(compile(original, '<released-piano-evaluator>', 'exec'), namespace)
    implementations = {'released': namespace['PianoModel'], 'candidate': PianoModel}
    spectrum = np.random.default_rng(5333).normal(0, .02, (1, 2050, 1723, 2)).astype('float32')
    report = {'baseline_commit': BASELINE, 'chip': subprocess.check_output(
        ['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
        'macos': platform.mac_ver()[0], 'device': mx.metal.device_info(),
        'weights_sha256': WEIGHTS['sha256'], 'input_shape': list(spectrum.shape),
        'notes': ['Model inference only, not file-to-WAV time or a musical quality test.',
                  'Full-context warm-up for each evaluator, then ABBA trials; no CPU fallback.',
                  'A virtual Metal device is not evidence of physical M3 performance.'], 'runs': []}
    reference = None
    try:
        for index, name in enumerate(('released', 'candidate', 'released', 'candidate', 'candidate', 'released')):
            model = implementations[name](path)
            try:
                mx.reset_peak_memory()
                start = time.monotonic()
                actual = model.predict(spectrum)
                elapsed = time.monotonic()-start
                peak = mx.get_peak_memory()
            finally:
                model.close()
            if not np.isfinite(actual).all():
                raise ValueError('The model returned non-finite samples.')
            if reference is None:
                reference = actual
            delta = actual.astype('float64')-reference
            error = {'rms': float(np.sqrt(np.mean(delta*delta))), 'max_abs': float(np.abs(delta).max())}
            run = {'evaluator': name, 'warmup': index < 2, 'seconds': elapsed,
                   'peak_mlx_allocated_bytes': peak, 'baseline_mask_error': error}
            report['runs'].append(run)
            print(json.dumps(run), flush=True)
            if error['rms'] >= 1e-5 or error['max_abs'] >= 1e-3:
                raise ValueError('The candidate failed full-context numerical parity.')
        report['median_seconds'] = {name: statistics.median(r['seconds'] for r in report['runs']
            if r['evaluator'] == name and not r['warmup']) for name in implementations}
        report['speedup'] = report['median_seconds']['released']/report['median_seconds']['candidate']
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
