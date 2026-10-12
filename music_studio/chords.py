"""Portable chord notation, transposition, key estimates, and real note sets."""
import math
import re

ROOTS = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
INTERVALS = {
    'maj': (0, 4, 7), 'min': (0, 3, 7), 'dim': (0, 3, 6), 'aug': (0, 4, 8),
    '7': (0, 4, 7, 10), 'maj7': (0, 4, 7, 11), 'min7': (0, 3, 7, 10),
    'minmaj7': (0, 3, 7, 11), 'dim7': (0, 3, 6, 9), 'hdim7': (0, 3, 6, 10),
    'maj6': (0, 4, 7, 9), 'min6': (0, 3, 7, 9), 'sus2': (0, 2, 7), 'sus4': (0, 5, 7),
    '9': (0, 4, 7, 10, 2), 'maj9': (0, 4, 7, 11, 2), 'min9': (0, 3, 7, 10, 2),
    '11': (0, 4, 7, 10, 2, 5), '13': (0, 4, 7, 10, 2, 5, 9),
}
ALIASES = {'': 'maj', 'm': 'min', 'M': 'maj', 'm7': 'min7', 'M7': 'maj7', 'm6': 'min6',
           '6': 'maj6', 'm9': 'min9', 'M9': 'maj9', 'm7b5': 'hdim7', '°': 'dim',
           'o': 'dim', '°7': 'dim7', 'o7': 'dim7', '+': 'aug', 'm(maj7)': 'minmaj7'}


def pitch(note):
    match = re.fullmatch(r'([A-G])([#b]?)', note)
    if not match:
        raise ValueError('Choose a note from A to G, with an optional sharp or flat.')
    value = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[match[1]]
    return (value + (1 if match[2] == '#' else -1 if match[2] == 'b' else 0)) % 12


def normalize(label):
    value = str(label).strip().replace('♯', '#').replace('♭', 'b')
    if value in ('N', 'X'):
        return value
    if len(value) > 32:
        raise ValueError('Chord label is too long.')
    match = re.fullmatch(r'([A-G][#b]?)(?::?([^/]*))?(?:/([A-G][#b]?))?', value)
    if not match:
        raise ValueError('Enter a chord such as C, Am, Fmaj7, or G7/B.')
    quality = ALIASES.get(match[2] or '', match[2] or '')
    if quality not in INTERVALS:
        raise ValueError('This chord quality is not supported.')
    return ROOTS[pitch(match[1])] + ':' + quality + ('/' + ROOTS[pitch(match[3])] if match[3] else '')


def transpose(label, semitones):
    value = normalize(label)
    if value in ('N', 'X'):
        return value
    root_quality, *bass = value.split('/')
    root, quality = root_quality.split(':')
    amount = int(semitones)
    return ROOTS[(pitch(root) + amount) % 12] + ':' + quality + ('/' + ROOTS[(pitch(bass[0]) + amount) % 12] if bass else '')


def notes(label):
    value = normalize(label)
    if value in ('N', 'X'):
        return []
    root_quality, *bass = value.split('/')
    root, quality = root_quality.split(':')
    result = {(pitch(root) + interval) % 12 for interval in INTERVALS[quality]}
    if bass:
        result.add(pitch(bass[0]))
    return sorted(result)


def estimate_key(events):
    histogram = [0.0] * 12
    for event in events:
        label = normalize(event['chord'])
        if label in ('N', 'X'):
            continue
        duration = event['end'] - event['start']
        for note in notes(label):
            histogram[note] += duration
    if sum(histogram) == 0:
        return None
    profiles = ([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
                [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    ranked = []
    mean = sum(histogram) / 12
    for mode, profile in zip(('major', 'minor'), profiles):
        average = sum(profile) / 12
        for root in range(12):
            a = [histogram[(root + i) % 12] - mean for i in range(12)]
            b = [value - average for value in profile]
            divisor = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
            score = sum(x * y for x, y in zip(a, b)) / divisor if divisor else 0
            ranked.append((score, ROOTS[root] + ' ' + mode))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked[0][0] >= .55 and ranked[0][0] - ranked[1][0] >= .04 else None
