"""Posterior grouping preserves musical distinctions and probability mass."""
import sys
from pathlib import Path
from collections.abc import Sequence
import json

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.evidence import grouped_candidates, _posterior
from music_studio.chords import normalize, notes, pitch


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



def reference_grouped_candidates(probabilities, labels: Sequence[str], bass_probabilities=None):
    """Return (existing label per frame, group confidence, group margin).

    ``probabilities`` is a normalized [frames, classes] posterior. Labels must
    use Blaze's supported chord vocabulary. The optional bass posterior has
    13 columns: no-bass followed by C, C#, ... B, matching LV-Chordia's head.

    The highest-probability existing label normally names the winning group.
    A bass probability of at least .6 may select a group member whose root
    matches that bass, provided its chord probability is at least .03 and
    one tenth of the group's highest class probability. No notes or labels
    are invented, and weak bass evidence never changes the selected name.
    Consumers apply their usual confidence/margin thresholds to the result.
    """
    if isinstance(labels, (str, bytes)):
        raise ValueError('Labels must be a nonempty sequence of chord names.')
    try:
        original = list(labels)
    except TypeError as error:
        raise ValueError('Labels must be a nonempty sequence of chord names.') from error
    if not original or not all(isinstance(label, str) for label in original):
        raise ValueError('Labels must be a nonempty sequence of chord names.')

    normalized = [normalize(label) for label in original]
    groups = {}
    roots = []
    for index, label in enumerate(normalized):
        if label in ('N', 'X'):
            key = ('sentinel', label)
            roots.append(-1)
        else:
            key = ('notes', tuple(notes(label)))
            roots.append(pitch(label.split(':', 1)[0]))
        groups.setdefault(key, []).append(index)
    indices = [np.asarray(group, dtype=np.intp) for group in groups.values()]
    posterior = _posterior(probabilities, len(original), 'Chord probabilities')
    bass = None if bass_probabilities is None else _posterior(
        bass_probabilities, 13, 'Bass probabilities', len(posterior))

    if not len(posterior):
        return [], np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32)

    # Each vocabulary column belongs to exactly one group. Summing here
    # partitions posterior mass and cannot duplicate evidence across groups.
    mass = np.column_stack([np.sum(posterior[:, group], axis=1) for group in indices])
    winning = np.argmax(mass, axis=1)
    confidence = mass[np.arange(len(posterior)), winning]
    second = np.zeros(len(posterior), np.float64) if len(indices) == 1 else np.partition(
        mass, -2, axis=1)[:, -2]
    margin = confidence - second

    result = []
    roots = np.asarray(roots, dtype=np.int8)
    for frame, winner in enumerate(winning):
        group = indices[winner]
        probabilities_in_group = posterior[frame, group]
        highest = float(np.max(probabilities_in_group))
        choice = int(group[np.argmax(probabilities_in_group)])
        if bass is not None:
            bass_index = int(np.argmax(bass[frame]))
            if bass_index > 0 and bass[frame, bass_index] >= .6:
                eligible = group[(roots[group] == bass_index - 1) &
                                 (probabilities_in_group >= max(.03, highest * .1))]
                if len(eligible):
                    choice = int(eligible[np.argmax(posterior[frame, eligible])])
        result.append(original[choice])
    return result, confidence.astype(np.float32), margin.astype(np.float32)

rng=np.random.default_rng(177)
model_labels=json.loads((Path(__file__).resolve().parents[1]/'music_studio/models/manifest.json').read_text())['models']['extended']['labels']
for dtype in (np.float32,np.float64):
    for count in (1,31,4097):
        posterior=rng.uniform(0,1,(count,len(model_labels))).astype(dtype)
        posterior/=posterior.sum(axis=1,keepdims=True)
        bass=rng.uniform(0,1,(count,13)).astype(dtype)
        bass/=bass.sum(axis=1,keepdims=True)
        bass[:min(count,13)]=.4/12
        for row in range(min(count,13)):bass[row,row]=.6
        for supplied in (None,bass):
            actual=grouped_candidates(posterior,model_labels,supplied)
            expected=reference_grouped_candidates(posterior,model_labels,supplied)
            assert actual[0]==expected[0]
            assert actual[1].tobytes()==expected[1].tobytes()
            assert actual[2].tobytes()==expected[2].tobytes()
# Exact ties keep the first original vocabulary member.
posterior=np.full((4097,len(model_labels)),1/len(model_labels))
assert grouped_candidates(posterior,model_labels)[0]==reference_grouped_candidates(posterior,model_labels)[0]

print('Chord evidence: equivalent sets, independent bass naming, mass partition, '
      'N/X distinction, real-note differences and invalid-input checks PASS')
