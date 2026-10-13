"""File-backed Android adapter for the exact shared Windows harmony decoder.

Java ONNX Runtime owns all neural sessions. This module uses only NumPy and
the copied, checked shared source files; no network access or model training.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from blaze_studio_shared.chords import estimate_key
from blaze_studio_shared.lv_frontend import PortableLVFrontend
from blaze_studio_shared.structured import StructuredRecognizer

HEAD_COLUMNS = (73, 13, 4, 4, 3, 3)


def _checked(path, digest):
    value = Path(path)
    if not value.is_file() or value.stat().st_size > 100 * 1024 ** 2:
        raise ValueError('Advanced model frontend is missing or too large.')
    if hashlib.sha256(value.read_bytes()).hexdigest() != digest:
        raise ValueError('Advanced model frontend verification failed.')
    return value


class Harmony:
    def __init__(self, directory, work_directory, pcm_path, samples, callback):
        self.directory = Path(directory)
        self.work = Path(work_directory)
        self.check = callback.run if callback is not None else lambda: None
        self.samples = int(samples)
        self.pcm = np.memmap(pcm_path, dtype='<f4', mode='r', shape=(self.samples,))
        self.manifest = json.loads((self.directory / 'structured_manifest.json').read_text(encoding='utf-8'))
        if self.manifest.get('feature_size') != 252 or len(self.manifest['models']) != 5:
            raise ValueError('Invalid advanced model bundle.')
        asset = self.manifest['frontend']
        self.frontend = PortableLVFrontend(_checked(self.directory / asset['file'], asset['sha256']))
        self.size = 0
        self.heads = []

    def prepare(self):
        self.check()
        all_features = self.frontend.extract(self.pcm, output_path=self.work / 'cqt.f32', check=self.check)
        self.size = len(all_features)
        # Network data is contiguous: Java can read each overlapping context.
        network = np.memmap(self.work / 'features.f32', dtype='<f4', mode='w+', shape=(self.size, 252))
        for start in range(0, self.size, 512):
            self.check()
            network[start:start + 512] = all_features[start:start + 512, 18:270]
        network.flush()
        self.weights = np.memmap(self.work / 'weights.f32', dtype='<f4', mode='w+', shape=(self.size,))
        self.weights[:] = 0
        for head, columns in enumerate(HEAD_COLUMNS):
            output = np.memmap(self.work / ('head-' + str(head) + '.f32'), dtype='<f4', mode='w+', shape=(self.size, columns))
            output[:] = 0
            self.heads.append(output)
        return json.dumps({'frames': self.size, 'features': str(self.work / 'features.f32'),
                           'tuning': self.frontend.last_tuning})

    def accumulate(self, path, start, count):
        self.check()
        start, count = int(start), int(count)
        if start < 0 or count <= 0 or start + count > self.size:
            raise ValueError('Invalid advanced model context.')
        raw = np.memmap(path, dtype='<f4', mode='r')
        if len(raw) != count * sum(HEAD_COLUMNS) or not np.all(np.isfinite(raw)):
            raise ValueError('Invalid advanced posterior shape.')
        weight = np.minimum(np.minimum(np.arange(count) + 1, np.arange(count, 0, -1)), 129) / 129
        offset = 0
        for destination, columns in zip(self.heads, HEAD_COLUMNS):
            size = count * columns
            source = raw[offset:offset + size].reshape(count, columns)
            if np.any(source < 0) or np.any(np.abs(source.sum(axis=1) - 1) > .001):
                raise ValueError('Invalid advanced posterior values.')
            destination[start:start + count] += source * weight[:, None]
            offset += size
        self.weights[start:start + count] += weight

    def finish(self, baseline_path, baseline_manifest, beats_ms):
        self.check()
        if np.any(self.weights <= 0):
            raise ValueError('Advanced inference did not cover every frame.')
        for start in range(0, self.size, 1024):
            self.check()
            for head in self.heads:
                head[start:start + 1024] /= self.weights[start:start + 1024, None]
        metadata = json.loads(baseline_manifest)
        labels = metadata['labels']
        baseline = np.memmap(baseline_path, dtype='<f4', mode='r').reshape(-1, len(labels))
        # Shared decoder constructor normally opens Python ORT. Android already
        # ran those exact networks in Java, so only its pure decode state is used.
        decoder = StructuredRecognizer.__new__(StructuredRecognizer)
        decoder.labels = [entry['label'] for entry in self.manifest['labels']]
        decoder.components = np.asarray([entry['components'] for entry in self.manifest['labels']], dtype=np.int32)
        decoder.components[:, 1] += 1
        frames = decoder.decode(self.heads, baseline, labels, self.samples / 22050,
                                [float(t) / 1000 for t in beats_ms], self.pcm, self.check)
        # Match the shared Windows final single-frame vote and bounded X bridge.
        names = [frame['chord'] for frame in frames]
        for index in range(1, len(frames) - 1):
            if names[index - 1] == names[index + 1] and names[index] != 'N':
                frames[index]['chord'] = names[index - 1]
                if names[index] != names[index - 1]:
                    frames[index]['model_score'] = None
        _bridge(frames)
        events = []
        for frame in frames:
            if events and events[-1]['chord'] == frame['chord']:
                event = events[-1]
                before, after = event['end'] - event['start'], frame['end'] - frame['start']
                event['model_score'] = ((event['model_score'] * before + frame['model_score'] * after) / (before + after)
                                        if event['model_score'] is not None and frame['model_score'] is not None else None)
                event['end'] = frame['end']
            else:
                events.append(dict(frame))
        self.check()
        return json.dumps({'key': estimate_key(events), 'events': events}, allow_nan=False)

    def close(self):
        # Release mappings before Java deletes this task's private work folder.
        for value in (*self.heads, getattr(self, 'weights', None), self.pcm):
            if value is not None:
                value._mmap.close()
        self.heads.clear()
        self.weights = None
        self.pcm = None


def _bridge(frames, max_gap=.28):
    index = 0
    while index < len(frames):
        if frames[index]['chord'] != 'X':
            index += 1
            continue
        start = index
        while index < len(frames) and frames[index]['chord'] == 'X':
            index += 1
        if start == 0 or index == len(frames):
            continue
        left, right = frames[start - 1]['chord'], frames[index]['chord']
        if left != right or left in ('X', 'N') or frames[index - 1]['end'] - frames[start]['start'] > max_gap:
            continue
        before, after = start - 1, index
        while before > 0 and frames[before - 1]['chord'] == left:
            before -= 1
        while after + 1 < len(frames) and frames[after + 1]['chord'] == right:
            after += 1
        if frames[start - 1]['end'] - frames[before]['start'] < .2 or frames[after]['end'] - frames[index]['start'] < .2:
            continue
        for frame in frames[start:index]:
            frame['chord'] = left
            frame['model_score'] = None
