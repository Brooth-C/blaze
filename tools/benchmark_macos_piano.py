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

BASELINE = '7b02980295a94fd797d83e126a42b641400539fe'  # Stable 0.19.5.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-tokens', type=int, choices=(0,16384,32768,65536),
                        help='Candidate only: compare full batching (0) with bounded independent batches.')
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
    report = {'baseline_commit': BASELINE, 'candidate_batch_tokens': args.batch_tokens,
        'chip': subprocess.check_output(
        ['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
        'macos': platform.mac_ver()[0], 'device': mx.metal.device_info(),
        'weights_sha256': WEIGHTS['sha256'], 'input_shape': list(spectrum.shape),
        'notes': ['Model inference only, not file-to-WAV time or a musical quality test.',
                  'Every fresh model is warmed before its timed sample; two ABBA rounds; no CPU fallback.',
                  'A virtual Metal device is not evidence of physical M3 performance.'], 'runs': []}
    reference = None
    try:
        order = ('released', 'candidate')+('released', 'candidate', 'candidate', 'released')*2
        for index, name in enumerate(order):
            model = implementations[name](path)
            try:
                if name == 'candidate' and args.batch_tokens is not None:
                    model.batch_tokens = args.batch_tokens
                # Compilation/cache state belongs to this model instance.
                # Warming a discarded instance does not warm the next one.
                warm_start = time.monotonic()
                warm = model.predict(spectrum)
                if not np.isfinite(warm).all():
                    raise ValueError('The GPU warm-up returned invalid samples.')
                del warm
                mx.synchronize(model.stream)
                warm_seconds = time.monotonic()-warm_start
                swap_before = subprocess.check_output(['sysctl','-n','vm.swapusage'],text=True).strip()
                mx.reset_peak_memory()
                start = time.monotonic()
                actual = model.predict(spectrum)
                elapsed = time.monotonic()-start
                peak = mx.get_peak_memory()
                batch_tokens = getattr(model,'batch_tokens',0)
                swap_after = subprocess.check_output(['sysctl','-n','vm.swapusage'],text=True).strip()
            finally:
                model.close()
            if not np.isfinite(actual).all():
                raise ValueError('The model returned non-finite samples.')
            if reference is None:
                reference = np.array(actual,copy=True)
            delta = actual.astype('float64')-reference
            error = {'rms': float(np.sqrt(np.mean(delta*delta))), 'max_abs': float(np.abs(delta).max())}
            run = {'evaluator': name, 'warmup': index < 2, 'seconds': elapsed,
                   'instance_warmup_seconds': warm_seconds, 'sequence_batch_tokens': batch_tokens,
                   'swap_before': swap_before, 'swap_after': swap_after,
                   'peak_mlx_allocated_bytes': peak, 'baseline_mask_error': error}
            report['runs'].append(run)
            print(json.dumps(run), flush=True)
            if error['rms'] >= 1e-5 or error['max_abs'] >= 1e-3:
                raise ValueError('The candidate failed full-context numerical parity.')
            del actual, delta
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
