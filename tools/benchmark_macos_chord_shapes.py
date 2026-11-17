"""Native experiment: compare dynamic chord graphs with exact input shapes.

Uses the app's checksum-pinned weights, full contexts and Core ML settings.
This diagnostic does not change the app runtime or promote an optimization.
Run on macOS 26 Apple Silicon; --output names a new JSON report file.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def asset(directory, manifest, select):
    supplied = select(json.loads((directory / manifest).read_text()))
    pinned = select(json.loads((ROOT / 'music_studio/models' / manifest).read_text()))
    if supplied['sha256'] != pinned['sha256'] or supplied['file'] != pinned['file']:
        raise ValueError('Use the production chord checkpoint pinned by this app revision.')
    name = supplied['file']
    if Path(name).name != name:
        raise ValueError('Model paths must remain inside the asset directory.')
    path = directory / name
    if path.stat().st_size > 100 * 1024 ** 2:
        raise ValueError('Chord experiment model exceeds the asset bound.')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != supplied['sha256']:
        raise ValueError('Production chord asset checksum mismatch.')
    return supplied, data


def inputs(kind, length):
    import numpy as np
    rng = np.random.default_rng(length)
    shape = (1, length) if kind == 'cqt' else (1, length, 252)
    normal = (rng.normal(0, .1, shape) if kind == 'cqt' else rng.uniform(0, 30, shape)).astype(np.float32)
    return [('normal', normal), ('quiet', normal * np.float32(1e-5)),
            ('silence', np.zeros(shape, np.float32))]


def comparison(actual, expected):
    import numpy as np
    if len(actual) != len(expected):
        raise ValueError('Candidate changed the number of model output heads.')
    heads = []
    for got, want in zip(actual, expected):
        if got.shape != want.shape or got.dtype != want.dtype:
            raise ValueError('Candidate changed a model output shape or precision.')
        if not np.isfinite(got).all() or not np.isfinite(want).all():
            raise ValueError('Model returned nonfinite values.')
        delta = got.astype(np.float64) - want.astype(np.float64)
        heads.append({'shape': list(got.shape), 'dtype': str(got.dtype),
                      'exact_bytes': got.tobytes() == want.tobytes(),
                      'max_abs_error': float(np.max(np.abs(delta), initial=0)),
                      'rms_error': float(np.sqrt(np.mean(delta * delta)))})
    return {'all_heads_exact': all(head['exact_bytes'] for head in heads), 'heads': heads}


def run_variant(kind, metadata, data, lengths, exact, repeats, artifacts, reference=None, report=None):
    import numpy as np
    import onnxruntime as ort
    from music_studio.stem_runtime import StemRuntime
    from tools.benchmark_macos_stems import provider_summary
    label = 'exact' if exact else 'dynamic'
    runtime = StemRuntime(backend='coreml', cache=artifacts / 'cache' / (kind + '-' + label),
                          profile=artifacts / 'profiles' / (kind + '-' + label))
    input_name, dimension = ('pcm', 'samples') if kind == 'cqt' else ('features', 'frames')
    outputs, session = {}, None
    if report is None:
        report = {}
    report.update(variant=label, sessions=[], cases=[])
    try:
        for length in lengths:
            if session is None:
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                started = time.perf_counter()
                session = runtime.session(data, options, metadata['sha256'],
                                          free_dimensions={dimension: length} if exact else None)
                report['sessions'].append({'input_length': length if exact else 'dynamic',
                                           'creation_seconds': time.perf_counter() - started,
                                           'input_shape': session.get_inputs()[0].shape})
            for name, value in inputs(kind, length):
                key = str(length) + ':' + name
                started = time.perf_counter()
                warm = session.run(None, {input_name: value})
                warm_seconds = time.perf_counter() - started
                samples, repeat_comparisons = [], []
                for _ in range(repeats):
                    started = time.perf_counter()
                    actual = session.run(None, {input_name: value})
                    samples.append(time.perf_counter() - started)
                    repeat_comparisons.append(comparison(actual, warm))
                outputs[key] = [np.array(head, copy=True) for head in actual]
                target = reference[key] if reference is not None else warm
                report['cases'].append({'input_length': length, 'signal': name,
                                        'warmup_seconds': warm_seconds, 'timed_seconds': samples,
                                        'median_seconds': statistics.median(samples),
                                        'all_repeats_exact': all(item['all_heads_exact'] for item in repeat_comparisons),
                                        'repeat_comparisons': repeat_comparisons,
                                        'comparison': comparison(actual, target)})
                case = report['cases'][-1]
                print(json.dumps({'model': kind, 'variant': label, 'input_length': length, 'signal': name,
                                  'warmup_seconds': warm_seconds, 'median_seconds': case['median_seconds'],
                                  'all_repeats_exact': case['all_repeats_exact'],
                                  'all_heads_exact': case['comparison']['all_heads_exact'],
                                  'max_abs_error': max(head['max_abs_error'] for head in case['comparison']['heads'])}),
                      flush=True)
            if exact:
                runtime.finish(session)
                session = None
                gc.collect()
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if session is not None:
            runtime.finish(session)
            session = None
        gc.collect()
        report['graphs'] = runtime.records
        report['provider_events'] = provider_summary(runtime.records)
    return outputs, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New JSON report file')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        parser.error('Run on an Apple Silicon Mac.')
    if int(platform.mac_ver()[0].split('.')[0]) < 26:
        parser.error('Run on macOS 26 or newer.')
    if not 1 <= args.repeats <= 10:
        parser.error('Choose 1–10 timed repetitions.')
    if args.output.exists():
        parser.error('Choose a new JSON report file.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = args.output.parent / (args.output.stem + '-artifacts')
    artifacts.mkdir(exist_ok=False)
    report = {'macos': platform.mac_ver()[0], 'architecture': platform.machine(),
              'experiments': [], 'promoted': False,
              'notes': ['Original weights, FP32 input and exact full contexts; no padding or quantization.',
                        'Only one inference session is live at a time.',
                        'Each variant starts with an isolated empty Core ML disk cache.',
                        'Provider events show delegated partitions, not proof of physical GPU utilization.',
                        'Profiling adds overhead; measurements do not establish whole-song M3 speed.',
                        'Only the first ensemble checkpoint is tested; this cannot approve all five models.']}
    try:
        import onnxruntime as ort
        report['onnxruntime'] = ort.__version__
        for kind, manifest, select, lengths in [
            ('cqt', 'manifest.json', lambda m: m['frontend'], (221184, 110593)),
            ('ensemble', 'structured_manifest.json', lambda m: m['models'][0], (1292, 290)),
        ]:
            metadata, data = asset(args.models, manifest, select)
            entry = {'model': kind, 'sha256': metadata['sha256'], 'dynamic': {}, 'exact': {}}
            report['experiments'].append(entry)
            reference, baseline = run_variant(kind, metadata, data, lengths, False, args.repeats, artifacts,
                                              report=entry['dynamic'])
            _, candidate = run_variant(kind, metadata, data, lengths, True, args.repeats, artifacts, reference,
                                        report=entry['exact'])
            entry['all_outputs_exact'] = all(case['comparison']['all_heads_exact'] and case['all_repeats_exact']
                                             for variant in (baseline, candidate) for case in variant['cases'])
            args.output.write_text(json.dumps(report, indent=2))
            print(json.dumps({'model': kind, 'all_outputs_exact': entry['all_outputs_exact'],
                              'dynamic_seconds': [case['median_seconds'] for case in baseline['cases']],
                              'exact_seconds': [case['median_seconds'] for case in candidate['cases']]}), flush=True)
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
