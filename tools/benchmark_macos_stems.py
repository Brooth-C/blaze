"""Measure actual Mac file-to-WAV time and provider delegation, never guess GPU use.

Run on macOS26 Apple Silicon. First run uses a fresh private CoreML disk cache;
subsequent runs reuse it. Profile kernel durations are not wall-clock timings.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def provider_summary(records):
    result = {}
    for record in records:
        if not record.get('profile'):
            continue
        for event in json.loads(Path(record['profile']).read_text()):
            provider = event.get('args', {}).get('provider')
            if event.get('cat') != 'Node' or not provider:
                continue
            entry = result.setdefault(provider, {'node_events': 0, 'sum_reported_microseconds': 0})
            entry['node_events'] += 1
            entry['sum_reported_microseconds'] += event.get('dur', 0)
    return result


def command(*args):
    return subprocess.check_output(args, text=True, timeout=10).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--backend', choices=['cpu', 'coreml'], default='cpu')
    parser.add_argument('--mode', choices=['piano', 'piano-legacy'], default='piano')
    parser.add_argument('--runs', type=int, choices=range(1, 6), default=2)
    args = parser.parse_args()
    if (sys.platform != 'darwin' or platform.machine().lower() != 'arm64'
            or platform.mac_ver()[0].split('.')[0] != '26'):
        parser.error('Measure Blaze stems on macOS26 Apple Silicon only.')
    if args.mode == 'piano-legacy' and args.backend != 'cpu':
        parser.error('The legacy Spleeter baseline uses CPU execution.')
    source = args.source.resolve(strict=True)
    if not source.is_file() or not 0 < source.stat().st_size <= 2 * 1024**3:
        parser.error('Choose a local recording smaller than 2 GB.')
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Choose a new empty benchmark output directory.')
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['BLAZE_STEM_BACKEND'] = args.backend
    from music_studio.native_piano import NativePianoSeparator
    from music_studio.piano import PianoSeparator
    from music_studio.stem_runtime import StemRuntime
    import onnxruntime as ort
    event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: event.set())
    duration = float(command('ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries', 'format=duration',
                             '-of', 'default=nw=1:nk=1', str(source)))
    if not math.isfinite(duration) or not duration > 0:
        parser.error('The recording duration must be positive.')
    with source.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'mode': args.mode, 'backend_requested': args.backend, 'ort': ort.__version__,
              'macos': platform.mac_ver()[0], 'chip': command('sysctl', '-n', 'machdep.cpu.brand_string'),
              'physical_memory_bytes': int(command('sysctl', '-n', 'hw.memsize')),
              'input_sha256': checksum, 'audio_seconds': duration,
              'notes': ['CoreML profile events prove delegation, not physical GPU utilization.',
                        'RSS is process-lifetime high-water, not a separate peak for each run.',
                        'Cold/warm refers to this fresh private compilation cache.',
                        'No musical quality or superiority is inferred from these timings.'], 'runs': []}
    try:
        for index in range(args.runs):
            engine = (NativePianoSeparator if args.mode == 'piano' else PianoSeparator)(args.models)
            if args.mode == 'piano':
                engine.runtime = StemRuntime(backend=args.backend, cache=args.output/'coreml-cache',
                                             profile=args.output/'profiles'/str(index))
            before = command('sysctl', 'vm.swapusage')
            start = time.monotonic()
            paths = engine.separate(source, args.output/('run-' + str(index)), cancel_event=event,
                                    progress=lambda f, m: print(json.dumps({'run': index, 'progress': f, 'message': m}), flush=True))
            elapsed = time.monotonic() - start
            records = engine.runtime.records if args.mode == 'piano' else []
            coverage = provider_summary(records)
            run = {'run': index, 'cache_state': 'fresh' if index == 0 else 'reused',
                   'file_to_wav_seconds': elapsed, 'time_over_audio_duration': elapsed/duration,
                   'process_lifetime_high_water_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   'swap_before': before, 'swap_after': command('sysctl', 'vm.swapusage'),
                   'provider_events': coverage, 'graphs': records,
                   'outputs': {name: path.stat().st_size for name, path in paths.items()}}
            report['runs'].append(run)
            if args.backend == 'coreml' and not coverage.get('CoreMLExecutionProvider', {}).get('node_events'):
                raise ValueError('No CoreML node execution was recorded; GPU acceleration is not established.')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output/'benchmark.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(args.output/'benchmark.json'), 'runs': len(report['runs'])}), flush=True)


if __name__ == '__main__':
    main()
