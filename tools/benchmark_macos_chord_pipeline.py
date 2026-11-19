"""Benchmark the complete app recognition worker using original production models.

Each sample starts a new process and app-data directory, so result-cache hits
cannot replace recognition. Core ML disk caches are isolated between released
and current code; fallback-thread candidates reuse the current compiled graphs.
No runtime policy is changed by this experiment.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'de0412b18618e16742563cbc2740a229f4da59aa'  # stable 0.19.6


def canonical_result(result):
    value = dict(result)
    value.pop('analysis_seconds', None)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def compare_results(actual, expected):
    """Keep strict equality and expose GPU score drift separately from music."""
    left, right = json.loads(actual), json.loads(expected)
    availability = True
    errors = []
    for got, wanted in zip(left.get('chords', []), right.get('chords', [])):
        a, b = got.get('model_score'), wanted.get('model_score')
        availability &= ('model_score' in got) == ('model_score' in wanted) and (a is None) == (b is None)
        if a is not None and b is not None:
            errors.append(abs(a - b))
    for result in (left, right):
        for chord in result.get('chords', []):
            chord.pop('model_score', None)
    return {'exact_bytes': actual == expected,
            'timeline_and_metadata_exact': left == right,
            'score_availability_exact': availability,
            'max_score_abs_error': max(errors, default=0.)}


def worker(args):
    sys.path.insert(0, str(args.code_root))
    os.environ['BLAZE_STEM_BACKEND'] = args.backend
    os.environ.pop('BLAZE_EXPERIMENTAL_CHORDMINI_DIR', None)
    os.environ.pop('BLAZE_STEM_PROFILE_DIR', None)
    import onnxruntime as ort
    from music_studio.stem_runtime import StemRuntime
    from music_studio.server import Studio
    runtimes = []
    original_init = StemRuntime.__init__
    original_session = ort.InferenceSession

    def initialize(self, backend=None, cache=None, profile=None):
        original_init(self, backend=backend, cache=cache or args.cache, profile=profile)
        runtimes.append(self)

    def inference(*positional, **keywords):
        providers = keywords.get('providers', [])
        if args.threads and any((provider[0] if isinstance(provider, tuple) else provider) ==
                                'CoreMLExecutionProvider' for provider in providers):
            keywords['sess_options'].intra_op_num_threads = args.threads
        return original_session(*positional, **keywords)

    StemRuntime.__init__ = initialize
    ort.InferenceSession = inference
    captured = io.StringIO()
    started = time.perf_counter()
    studio = None
    try:
        with contextlib.redirect_stdout(captured):
            studio = Studio(args.output / 'app-data', args.ffmpeg, args.source, args.models)
            studio.presentation = 'mac'
            studio.analyze('powerful')
            studio.worker.join(1200)
            if studio.worker.is_alive():
                studio.cancel_analysis()
                raise TimeoutError('Recognition exceeded the benchmark time limit.')
            elapsed = time.perf_counter() - started
        if studio.state['analysisTask']['status'] != 'done':
            raise RuntimeError(studio.state['analysisTask'].get('error', 'Recognition did not finish.'))
        result = studio.state['result']
        encoded = canonical_result(result)
        (args.output / 'result.json').write_bytes(encoded)
        stages = {}
        for line in captured.getvalue().splitlines():
            for prefix, name in [('BLAZE_ANALYSIS_TIMING ', 'recognition'),
                                 ('BLAZE_ANALYSIS_JOB_TIMING ', 'worker')]:
                if line.startswith(prefix):
                    stages[name] = json.loads(line[len(prefix):])
        records = [record for runtime in runtimes for record in runtime.records]
        entry = {'total_seconds': elapsed, 'duration_seconds': result['duration'],
                 'first_chords_seconds': stages.get('worker', {}).get('first_chords_seconds', elapsed),
                 'result_sha256': hashlib.sha256(encoded).hexdigest(), 'stages': stages,
                 'session_creation_seconds': sum(r['session_creation_seconds'] for r in records),
                 'graphs': records, 'fallback_thread_override': args.threads or None}
        (args.output / 'measurement.json').write_text(json.dumps(entry, indent=2))
        print(json.dumps(entry), flush=True)
    finally:
        if studio is not None:
            studio.close()
        (args.output / 'worker.log').write_text(captured.getvalue())


def snapshot(destination):
    archive = destination.parent / 'released-source.tar'
    subprocess.run(['git', '-C', str(ROOT), 'archive', '--format=tar', '--output', str(archive),
                    BASELINE, 'music_studio'], check=True)
    destination.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--backend', choices=('coreml', 'cpu'), default='coreml')
    parser.add_argument('--runs', type=int, default=2, help='Warm runs after the first invocation')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--code-root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--cache', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--threads', type=int, choices=(0, 1, 2, 4), default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        parser.error('Run on an Apple Silicon Mac.')
    if int(platform.mac_ver()[0].split('.')[0]) < 26:
        parser.error('Run on macOS 26 or newer.')
    args.source = args.source.resolve(strict=True)
    args.models = args.models.resolve(strict=True)
    args.output = args.output.resolve()
    if args.worker:
        args.output.mkdir(parents=True, exist_ok=False)
        worker(args)
        return
    if not 1 <= args.runs <= 5:
        parser.error('Choose 1–5 warm runs.')
    args.output.mkdir(parents=True, exist_ok=False)
    released = args.output / 'released-source'
    snapshot(released)
    variants = [('released', released, 0, 'released'), ('current', ROOT, 0, 'current')]
    if args.backend == 'coreml':
        variants += [('threads2', ROOT, 2, 'current'), ('threads4', ROOT, 4, 'current')]
    report = {'backend': args.backend, 'baseline_commit': BASELINE, 'macos': platform.mac_ver()[0], 'runs': [],
              'notes': ['Total app worker time includes input copying, model verification, inference and saving.',
                        'Every sample bypasses result reuse using new app data.',
                        'No profiling is enabled for timed measurements.',
                        'Thread variants reuse current Core ML disk cache; they have no cold-cache measurement.',
                        'Hosted runner performance is not a measurement of the user M3.']}
    reference = None
    try:
        for repeat in range(args.runs + 1):
            order = variants if repeat % 2 == 0 else list(reversed(variants))
            for name, code, threads, cache in order:
                out = args.output / (name + '-' + str(repeat))
                command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--source', str(args.source),
                           '--models', str(args.models), '--output', str(out), '--ffmpeg', args.ffmpeg,
                           '--code-root', str(code), '--cache', str(args.output / 'cache' / cache),
                           '--threads', str(threads), '--backend', args.backend]
                process = subprocess.run(command, capture_output=True, text=True, timeout=1250)
                (args.output / (name + '-' + str(repeat) + '.log')).write_text(process.stdout + process.stderr)
                if process.returncode:
                    raise RuntimeError('Worker failed for ' + name + ': ' + process.stderr[-2000:])
                value = json.loads((out / 'measurement.json').read_text())
                encoded = (out / 'result.json').read_bytes()
                if reference is None:
                    reference = encoded
                value['result_comparison'] = compare_results(encoded, reference)
                value.update(variant=name, repeat=repeat, output_exact=encoded == reference,
                             cache_state=('cold' if repeat == 0 and name in ('released', 'current') else
                                          'first_with_reused_cache' if repeat == 0 else 'warm'))
                report['runs'].append(value)
                print('BLAZE_FULL_CHORD ' + json.dumps(value), flush=True)
                (args.output / 'report.json').write_text(json.dumps(report, indent=2))
        report['summary'] = {}
        for name, *_ in variants:
            rows = [row for row in report['runs'] if row['variant'] == name]
            warm = [row['total_seconds'] for row in rows if row['repeat'] > 0]
            first_chords = [row['first_chords_seconds'] for row in rows if row['repeat'] > 0]
            report['summary'][name] = {'median_warm_seconds': statistics.median(warm),
                                       'median_first_chords_seconds': statistics.median(first_chords),
                                       'all_results_exact': all(row['output_exact'] for row in rows),
                                       'timeline_and_metadata_exact': all(row['result_comparison']['timeline_and_metadata_exact'] for row in rows),
                                       'score_availability_exact': all(row['result_comparison']['score_availability_exact'] for row in rows),
                                       'max_score_abs_error': max(row['result_comparison']['max_score_abs_error'] for row in rows)}
        print('BLAZE_FULL_CHORD_SUMMARY ' + json.dumps(report['summary']), flush=True)
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
