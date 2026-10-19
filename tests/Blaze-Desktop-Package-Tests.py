"""Test the actual Windows/Linux entry point, embedded models and rendered UI."""
from pathlib import Path
import argparse
import json
import math
import struct
import subprocess
import wave


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    audio = work / 'Package-chords.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
        notes = [(60, 64, 67, 71), (57, 60, 64, 67), (62, 65, 69, 72), (55, 59, 62, 65)]
        for i in range(22050 * 12):
            chord = notes[min(3, i // (3 * 22050))]
            value = sum(math.sin(2 * math.pi * 440 * 2 ** ((n - 69) / 12) * i / 22050) for n in chord)
            output.writeframesraw(struct.pack('<h', int(value * 5000)))
    analysis = work / 'analysis.json'
    subprocess.run([str(args.app.resolve()), str(audio), '--self-test', str(analysis)], check=True, timeout=240)
    result = json.loads(analysis.read_text(encoding='utf-8'))
    assert result['chords'] and 'Ensemble' in str(result['model'])
    assert analysis.with_suffix('.csv').is_file()
    report = work / 'native-ui.json'
    try:
        process = subprocess.run([str(args.app.resolve()), str(audio), '--ui-smoke', str(report)], timeout=360)
    finally:
        log = work / 'ui-smoke-data/desktop.log'
        if log.is_file():
            print(log.read_text(encoding='utf-8')[-10000:], flush=True)
    receipt = json.loads(report.read_text(encoding='utf-8'))
    print(json.dumps(receipt, indent=2), flush=True)
    assert process.returncode == 0 and receipt['ok'], receipt
    assert receipt['download']['status'] == 'done'
    assert receipt['seek'] and receipt['diagram_count'] == 3
    assert report.with_suffix('.png').stat().st_size > 100
    print('PACKAGED APP PASS: model inference, edit/export, native launch, local download, playback, seek, layouts.')


if __name__ == '__main__':
    main()
