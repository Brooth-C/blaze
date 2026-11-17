"""Measure complete chord recognition and actual ONNX provider placement on Mac.

Uses the existing model settings. Core ML profile events indicate delegated
partitions, not a claim that every operation ran on the GPU. Profiling adds
some overhead; this diagnostic is not a release speed benchmark by itself.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_macos_stems import provider_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory for local diagnostics')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--backend', choices=('coreml', 'cpu'), default='coreml')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine().lower() not in ('arm64', 'aarch64'):
        parser.error('Run on an Apple Silicon Mac.')
    if int(platform.mac_ver()[0].split('.')[0]) < 26:
        parser.error('Run on macOS 26 or newer.')
    if not 1 <= args.runs <= 10 or not args.ffmpeg:
        parser.error('Choose 1–10 runs and an available FFmpeg executable.')
    source = args.source.resolve(strict=True)
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['BLAZE_STEM_BACKEND'] = args.backend
    from music_studio.engine import Analyzer, ModelBundle
    report = {'backend': args.backend, 'macos': platform.mac_ver()[0], 'runs': [],
              'notes': ['Includes source hashing and model verification.',
                        'Uses the app Core ML disk cache; its initial state is not assumed cold.',
                        'Provider event times are not wall-clock times; profiling adds overhead.']}
    try:
        for number in range(args.runs):
            os.environ['BLAZE_STEM_PROFILE_DIR'] = str(args.output / 'profiles' / str(number))
            bundle = analyzer = None
            started = time.perf_counter()
            try:
                bundle = ModelBundle(args.models, 'powerful')
                verified = time.perf_counter()
                analyzer = Analyzer(bundle, args.ffmpeg)
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    result = analyzer.analyze(source)
                elapsed = time.perf_counter() - started
            finally:
                if bundle is not None:
                    bundle.close()
            stages = [json.loads(line.split(' ', 1)[1]) for line in captured.getvalue().splitlines()
                      if line.startswith('BLAZE_ANALYSIS_TIMING ')]
            runtimes = [bundle.runtime, bundle.structured.runtime]
            if bundle.frontend.runtime is not bundle.runtime:
                runtimes.append(bundle.frontend.runtime)
            if analyzer.rhythm:
                runtimes.append(analyzer.rhythm.runtime)
            records = [record for runtime in runtimes for record in runtime.records]
            result.pop('analysis_seconds', None)
            result_bytes = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
            (args.output / ('result-' + str(number) + '.json')).write_bytes(result_bytes)
            entry = {'run': number, 'total_seconds': elapsed,
                     'model_verification_seconds': verified - started,
                     'audio_duration_seconds': result['duration'], 'stages': stages,
                     'provider_events': provider_summary(records), 'graphs': records,
                     'process_lifetime_high_water_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                     'result_sha256': hashlib.sha256(result_bytes).hexdigest()}
            report['runs'].append(entry)
            print(json.dumps(entry), flush=True)
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
