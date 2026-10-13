"""Parity checks for the streamed Android Beat This! frontend against Windows."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from music_studio.rhythm import MelAccumulator

spec = importlib.util.spec_from_file_location('blaze_rhythm', ROOT / 'android/app/src/main/python/blaze_rhythm.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
frontend = (ROOT / 'music_studio/models/beat_mel.npz').read_bytes()
with np.load(ROOT / 'music_studio/models/beat_mel.npz', allow_pickle=False) as values:
    window, filters = values['window'].copy(), values['filter'].copy()

rng = np.random.default_rng(87)
maximum_error = 0.0
for count in (0, 512, 513, 1024, 22050 * 7 + 173, 22050 * 31 + 71):
    pcm = rng.normal(0, .1, count).astype('<f4')
    reference = MelAccumulator(window, filters)
    for chunk in np.array_split(pcm, 13):
        reference.feed(chunk)
    expected = reference.finish()
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        (path / 'pcm').write_bytes(pcm.tobytes())
        info = json.loads(bridge.prepare_rhythm(str(path / 'pcm'), frontend, str(path / 'features'), count))
        actual = np.fromfile(path / 'features', dtype='<f4').reshape(-1, 128)
        assert info['frames'] == len(expected)
        assert actual.shape == expected.shape, (count, actual.shape, expected.shape)
        error = float(np.max(np.abs(actual - expected), initial=0))
        maximum_error = max(maximum_error, error)
        assert error < .00001, (count, error)
        if len(expected) >= 200:
            starts = np.arange(-6, len(expected) - 6, 1488)
            if len(expected) > 1488:
                starts[-1] = len(expected) - 1494
            for start in starts:
                wanted = expected[max(start, 0):min(start + 1500, len(expected))]
                wanted = np.pad(wanted, ((max(0, -start), max(0, min(6, start + 1500 - len(expected)))), (0, 0)))
                found = np.frombuffer(bridge.rhythm_chunk(str(path / 'features'), len(expected), start), dtype='<f4').reshape(-1, 128)
                assert found.shape == wanted.shape
                assert np.max(np.abs(found - wanted), initial=0) < .00001

class Cancelled(Exception):
    pass

class Check:
    def run(self):
        raise Cancelled()

with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    pcm = np.zeros(22050 * 5, dtype='<f4')
    (path / 'pcm').write_bytes(pcm.tobytes())
    try:
        bridge.prepare_rhythm(str(path / 'pcm'), frontend, str(path / 'features'), len(pcm), Check())
        raise AssertionError('Cancellation was ignored')
    except Cancelled:
        pass

print(f'Android streamed rhythm frontend: short and multi-chunk parity, exact overlap/padding, cancellation PASS; max error {maximum_error:.8g}')
