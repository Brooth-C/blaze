"""Posterior grouping preserves musical distinctions and probability mass."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.evidence import grouped_candidates


def check_values(actual, expected):
    assert np.allclose(actual, expected, atol=1e-6), (actual, expected)


def bass_at(note_index, strength):
    result = np.full((1, 13), (1 - strength) / 12)
    result[0, note_index + 1] = strength
    return result


def rejects(probabilities, labels, bass=None):
    try:
        grouped_candidates(probabilities, labels, bass)
    except ValueError:
        return
    raise AssertionError('Invalid input was accepted')


labels = ['C:dim7', 'D#:dim7', 'F#:dim7', 'A:dim7', 'G:maj', 'N', 'X']
p = np.array([[.20, .22, .18, .20, .08, .06, .06]])
chosen, confidence, margin = grouped_candidates(p, labels)
assert chosen == ['D#:dim7']
check_values(confidence, [.8])
check_values(margin, [.72])
assert np.array_equal(p, np.array([[.20, .22, .18, .20, .08, .06, .06]]))

# Root naming can follow strong independently supported bass without changing
# the winning set or attributing evidence to an unsupported chord.
chosen_bass, same_confidence, same_margin = grouped_candidates(p, labels, bass_at(0, .8))
assert chosen_bass == ['C:dim7']
check_values(same_confidence, confidence)
check_values(same_margin, margin)
assert grouped_candidates(p, labels, bass_at(0, .59))[0] == ['D#:dim7']
assert grouped_candidates(p, labels, bass_at(4, .9))[0] == ['D#:dim7']  # E outside set
negligible = np.array([[.001, .35, .20, .249, .08, .06, .06]])
assert grouped_candidates(negligible, labels, bass_at(0, .9))[0] == ['D#:dim7']

for labels, probabilities, expected in [
    (['C:maj6', 'A:min7', 'G:7', 'N', 'X'], [[.32, .40, .18, .05, .05]], 'A:min7'),
    (['C:hdim7', 'D#:min6', 'G:7', 'N', 'X'], [[.35, .41, .14, .05, .05]], 'D#:min6'),
    (['C:aug', 'E:aug', 'G#:aug', 'G:maj', 'N'], [[.20, .3, .28, .12, .10]], 'E:aug'),
    (['C:sus2', 'G:sus4', 'C:maj', 'N'], [[.25, .4, .25, .1]], 'G:sus4'),
]:
    chosen, confidence, _ = grouped_candidates(probabilities, labels)
    assert chosen == [expected]
    assert confidence[0] > max(probabilities[0])

assert grouped_candidates([[.40, .32, .18, .05, .05]],
                          ['C:maj6', 'A:min7', 'G:7', 'N', 'X'], bass_at(9, .8))[0] == ['A:min7']
assert grouped_candidates([[.35, .41, .14, .05, .05]],
                          ['C:hdim7', 'D#:min6', 'G:7', 'N', 'X'], bass_at(0, .8))[0] == ['C:hdim7']

# Near-related chords with additional/changed notes must remain competitors.
chosen, confidence, margin = grouped_candidates([[.28, .27, .25, .1, .1]],
                                                ['C:maj', 'C:min', 'C:maj7', 'N', 'X'])
assert chosen == ['C:maj']
check_values(confidence, [.28])
check_values(margin, [.01])
check_values(grouped_candidates([[.4, .35, .25]], ['C:7', 'C:9', 'C:11'])[1], [.4])
check_values(grouped_candidates([[.4, .35, .25]], ['C:maj', 'C:maj/F#', 'N'])[1], [.4])

# N and X never combine merely because neither has a pitch-class set.
chosen, confidence, margin = grouped_candidates([[.15, .2, .35, .3]], ['C:maj6', 'A:min7', 'N', 'X'])
check_values(confidence, [.35])
check_values(margin, [0])
assert grouped_candidates([[.03, .02, .85, .1]], ['C:maj6', 'A:min7', 'N', 'X'])[0] == ['N']
assert grouped_candidates([[.03, .02, .1, .85]], ['C:maj6', 'A:min7', 'N', 'X'])[0] == ['X']

# Vocabulary aliases and duplicate spellings partition each input column once.
chosen, confidence, margin = grouped_candidates([[.4, .3, .3]], ['C:maj', 'C', 'C:maj'])
assert chosen == ['C:maj']
check_values(confidence, [1])
check_values(margin, [1])
chosen, confidence, margin = grouped_candidates([[1.0000001, 0]], ['C:maj', 'N'])
check_values(confidence, [1])
assert confidence[0] <= 1

# Zero frames are valid, but missing/invalid vocabularies or malformed
# posteriors are rejected instead of generating labels from absent evidence.
empty = grouped_candidates(np.empty((0, 2)), ['C:maj', 'N'], np.empty((0, 13)))
assert empty[0] == [] and empty[1].shape == empty[2].shape == (0,)
for probabilities, labels in [([], ['C:maj']), (np.empty((0, 0)), []),
                             ([[.5, .5]], ['C:maj']), ([[1]], 'C:maj'),
                             ([[1]], ['bad']), ([[1]], [None]),
                             ([[.5, -.5]], ['C:maj', 'N']),
                             ([[np.nan, 0]], ['C:maj', 'N']),
                             ([[np.inf, 0]], ['C:maj', 'N']),
                             ([[.8, .8]], ['C:maj', 'N']),
                             ([[0, 0]], ['C:maj', 'N']),
                             ([[1j, 0]], ['C:maj', 'N'])]:
    rejects(probabilities, labels)
rejects([[1]], ['C:maj'], np.ones((1, 12)) / 12)
rejects([[1]], ['C:maj'], np.ones((2, 13)) / 13)
rejects([[1]], ['C:maj'], np.zeros((1, 13)))

print('Chord evidence: equivalent sets, independent bass naming, mass partition, '
      'N/X distinction, real-note differences and invalid-input checks PASS')
