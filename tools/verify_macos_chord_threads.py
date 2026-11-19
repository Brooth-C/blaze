"""Compare original Core ML chord outputs across CPU fallback thread counts.

A native diagnostic only: this does not change app settings, model graphs,
precision or context lengths. It reports exact output parity, not a speed claim.
Use the full-pipeline experiment to establish whether any candidate is useful.
"""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verified_asset(directory, manifest_name, select):
    supplied = select(json.loads((directory / manifest_name).read_text()))
    pinned = select(json.loads((ROOT / 'music_studio/models' / manifest_name).read_text()))
    name = supplied['file']
    if (Path(name).name != name or supplied['file'] != pinned['file']
            or supplied['sha256'] != pinned['sha256']):
        raise ValueError('Use the original neural chord model pinned by this app revision.')
    path = directory / name
    if not path.is_file() or path.stat().st_size > 200 * 1024**2:
        raise ValueError('Neural chord asset is missing or exceeds its size bound.')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pinned['sha256']:
        raise ValueError('Neural chord asset checksum mismatch.')
    return pinned, data


def model_specs():
    # These are exactly the neural graphs used by the supported powerful mode.
    # The LV frames stay dynamic: specializing them changed quiet/silent logits.
    yield 'btc-170', 'manifest.json', lambda m: m['models']['extended'], 'features', (108,), 144, None
    for index in range(5):
        yield ('ensemble-' + str(index), 'structured_manifest.json',
               lambda m, index=index: m['models'][index], 'features', (1292, 290), 252, None)
    yield 'rhythm', 'rhythm_manifest.json', lambda m: m['network'], 'spect', (1500,), 128, 'frames'


def signal_cases(model, frames, width):
    import numpy as np
    rng = np.random.default_rng(frames + width)
    shape = (1, frames, width)
    if model == 'btc-170':
        normal = rng.normal(0, 1, shape).astype(np.float32)
    else:
        normal = rng.uniform(0, 7 if model == 'rhythm' else 30, shape).astype(np.float32)
    return [('normal', normal), ('quiet', normal * np.float32(1e-5)),
            ('silence', np.zeros(shape, np.float32))]


def compare_outputs(actual, expected):
    import numpy as np
    if len(actual) != len(expected):
        raise ValueError('A candidate changed the number of neural output heads.')
    comparisons = []
    for head, (got, wanted) in enumerate(zip(actual, expected)):
        if got.shape != wanted.shape or got.dtype != wanted.dtype:
            raise ValueError('A candidate changed neural output shape or precision.')
        if not np.isfinite(got).all() or not np.isfinite(wanted).all():
            raise ValueError('A neural output contains nonfinite values.')
        delta = got.astype(np.float64) - wanted.astype(np.float64)
        comparisons.append({'head': head, 'shape': list(got.shape), 'dtype': str(got.dtype),
                            'exact_bytes': got.tobytes() == wanted.tobytes(),
                            'max_abs_error': float(np.max(np.abs(delta), initial=0)),
                            'rms_error': float(np.sqrt(np.mean(delta * delta)))})
    return {'all_heads_exact': all(item['exact_bytes'] for item in comparisons), 'heads': comparisons}


def run_model(metadata, data, name, input_name, lengths, width, static_dimension,
              threads, cache, reference=None, entry=None):
    import numpy as np
    import onnxruntime as ort
    from music_studio.stem_runtime import StemRuntime
    runtime = StemRuntime(backend='coreml', cache=cache)
    session, outputs = None, {}
    if entry is None:
        entry = {}
    entry.update(threads=threads, cases=[], all_outputs_exact=True)
    original_factory = ort.InferenceSession

    def create_session(*args, **kwargs):
        # StemRuntime intentionally sets one fallback thread. Override only the
        # experiment's newly-created options, after that assignment and before
        # ORT snapshots them. Core ML provider settings and graph stay unchanged.
        options = kwargs.get('sess_options')
        if options is None:
            raise ValueError('The diagnostic requires explicit session options.')
        options.intra_op_num_threads = threads
        return original_factory(*args, **kwargs)

    try:
        for frames in lengths:
            if session is None:
                options = ort.SessionOptions()
                options.intra_op_num_threads = threads
                options.inter_op_num_threads = 1
                options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                dimensions = {static_dimension: frames} if static_dimension else None
                with patch('music_studio.stem_runtime.ort.InferenceSession', side_effect=create_session):
                    session = runtime.session(data, options, metadata['sha256'], free_dimensions=dimensions)
                if session.get_session_options().intra_op_num_threads != threads:
                    raise ValueError('ORT did not use the requested experimental thread count.')
            for signal, value in signal_cases(name, frames, width):
                key = str(frames) + ':' + signal
                warm = session.run(None, {input_name: value})
                actual = session.run(None, {input_name: value})
                repeat = compare_outputs(actual, warm)
                comparison = compare_outputs(actual, reference[key] if reference is not None else warm)
                exact = repeat['all_heads_exact'] and comparison['all_heads_exact']
                entry['all_outputs_exact'] &= exact
                entry['cases'].append({'frames': frames, 'signal': signal, 'comparison': comparison,
                                       'repeat_comparison': repeat})
                outputs[key] = [np.array(head, copy=True) for head in actual]
                print(json.dumps({'model': name, 'threads': threads, 'frames': frames, 'signal': signal,
                                  'all_outputs_exact': exact,
                                  'max_abs_error': max(item['max_abs_error'] for item in comparison['heads'])}),
                      flush=True)
            if static_dimension:
                runtime.finish(session)
                session = None
                gc.collect()
    except BaseException as error:
        entry['all_outputs_exact'] = False
        entry['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if session is not None:
            runtime.finish(session)
            session = None
        gc.collect()
        entry['graphs'] = runtime.records
    return outputs, entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True, help='Existing app Core ML cache for compiled-graph reuse')
    parser.add_argument('--output', type=Path, required=True, help='New JSON report file')
    parser.add_argument('--threads', type=int, nargs='+', default=[2, 4])
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        parser.error('Run on an Apple Silicon Mac.')
    if int(platform.mac_ver()[0].split('.')[0]) < 26:
        parser.error('Run on macOS 26 or newer.')
    if not args.threads or any(value not in (2, 4) for value in args.threads):
        parser.error('Candidate thread counts must be 2 or 4.')
    if args.output.exists():
        parser.error('Choose a new JSON report file.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    os.environ.pop('BLAZE_STEM_PROFILE_DIR', None)
    candidates = list(dict.fromkeys(args.threads))
    report = {'macos': platform.mac_ver()[0], 'architecture': platform.machine(),
              'reference_threads': 1, 'candidate_threads': candidates, 'models': [],
              'exact_by_threads': {str(count): True for count in candidates},
              'promoted': False, 'complete': False,
              'notes': ['Raw outputs compared before softmax or decoding; no tolerance relaxed.',
                        'Original models, providers, precision, static/dynamic shape settings and contexts.',
                        'Only one neural session is live at a time; supplied cache is reused.',
                        'No timings are collected and no app policy is selected by this diagnostic.']}
    try:
        import onnxruntime as ort
        report['onnxruntime'] = ort.__version__
        for name, manifest, select, input_name, lengths, width, static_dimension in model_specs():
            metadata, data = verified_asset(args.models, manifest, select)
            entry = {'name': name, 'sha256': metadata['sha256'], 'variants': []}
            report['models'].append(entry)
            reference = None
            for count in (1, *candidates):
                variant = {}
                entry['variants'].append(variant)
                outputs, variant = run_model(metadata, data, name, input_name, lengths, width,
                                             static_dimension, count, args.cache, reference, entry=variant)
                if count == 1:
                    if not variant['all_outputs_exact']:
                        raise ValueError('Original one-thread inference is not byte-stable between repeats.')
                    reference = outputs
                else:
                    report['exact_by_threads'][str(count)] &= variant['all_outputs_exact']
            args.output.write_text(json.dumps(report, indent=2))
        report['complete'] = True
        print(json.dumps({'exact_by_threads': report['exact_by_threads'], 'complete': True, 'promoted': False}), flush=True)
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
