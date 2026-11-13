"""Run explicit local model candidates and record complete job time/provenance.

Native Core ML/MLX measurements require macOS26 Apple Silicon. --reference-cpu
is for chord-conversion validation on other hosts, not Mac speed claims.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['chordmini','chords-current','native-scnet','scnet-current','piano-current'],required=True)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runs',type=int,choices=range(1,6),default=2)
    parser.add_argument('--ffmpeg',default='ffmpeg')
    parser.add_argument('--reference-cpu',action='store_true')
    args = parser.parse_args()
    if args.reference_cpu:
        if args.kind not in ('chordmini','chords-current'):
            parser.error('CPU reference is only for chord conversion checks.')
        os.environ['BLAZE_STEM_BACKEND'] = 'cpu'
    elif sys.platform != 'darwin' or platform.machine().lower() != 'arm64' or platform.mac_ver()[0].split('.')[0] != '26':
        parser.error('Native performance measurements require macOS26 Apple Silicon.')
    source = args.source.resolve(strict=True)
    if args.output.exists():
        parser.error('Choose a new output directory.')
    args.output.mkdir(parents=True)
    with source.open('rb') as stream:
        checksum = hashlib.file_digest(stream,'sha256').hexdigest()
    report = {'kind':args.kind,'source_sha256':checksum,
              'host':platform.platform(),'reference_cpu':args.reference_cpu,'runs':[],
              'notes':['Full job includes model loading and output writing.',
                       'RSS is process lifetime high-water, not per-run allocation.',
                       'No accuracy or quality superiority is inferred.']}
    event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_:event.set())
    try:
        for index in range(args.runs):
            folder = args.output / str(index)
            folder.mkdir()
            started = time.perf_counter()
            if args.kind in ('chordmini','chords-current'):
                from music_studio.engine import Analyzer, ModelBundle
                if args.kind == 'chordmini':
                    from music_studio.chordmini import ChordMiniBundle, ChordMiniAnalyzer
                    engine = ChordMiniAnalyzer(ChordMiniBundle(args.models),args.ffmpeg)
                else:
                    engine = Analyzer(ModelBundle(args.models,'powerful'),args.ffmpeg)
                # Analyzer cancellation remains independent of the separator.
                def cancel_analysis(active=engine):
                    while not done.wait(.05):
                        if event.is_set():
                            active.cancel()
                            return
                done = threading.Event()
                watcher = threading.Thread(target=cancel_analysis,daemon=True)
                watcher.start()
                try:
                    result = engine.analyze(source)
                    from music_studio.store import validate
                    validate(result)
                    (folder/'analysis.json').write_text(json.dumps(result,indent=2))
                finally:
                    done.set()
                    watcher.join()
                duration = result['duration']
                provenance = dict(result['model'],phases=getattr(engine,'timings',{}))
            else:
                if args.kind == 'native-scnet':
                    from music_studio.native_scnet import NativeSCNetSeparator
                    engine = NativeSCNetSeparator(args.models,args.ffmpeg)
                elif args.kind == 'scnet-current':
                    from music_studio.stems import Separator
                    engine = Separator(args.models,args.ffmpeg)
                else:
                    from music_studio.mlx_piano import MlxPianoSeparator
                    engine = MlxPianoSeparator(args.models,args.ffmpeg)
                outputs = engine.separate(source,folder/'tracks',cancel_event=event)
                # All current separation outputs are IEEE-float stereo44100Hz.
                duration = (next(iter(outputs.values())).stat().st_size-58)/(44100*8)
                provenance = {'runtime_records':engine.runtime.records}
                if hasattr(engine,'mlx_records'):
                    provenance['mlx_records'] = engine.mlx_records
            elapsed = time.perf_counter()-started
            report['runs'].append({'seconds':elapsed,'audio_seconds':duration,'real_time_factor':elapsed/duration,
                                   'peak_rss_native_units':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                   'provenance':provenance})
    except BaseException as error:
        report['error'] = str(error) or type(error).__name__
        raise
    finally:
        (args.output/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print(args.output/'benchmark.json')


if __name__ == '__main__':
    main()
