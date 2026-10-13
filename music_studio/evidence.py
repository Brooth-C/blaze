"""Combine posterior evidence for labels describing the same pitch classes.

For example, Cdim7 and Ebdim7 have identical pitch-class sets. Their class
probabilities therefore provide evidence for one sounding set, rather than
competing hypotheses about different notes. Confidence is posterior mass for
that set, not a calibrated correctness probability. N and X remain separate.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .chords import normalize, notes, pitch


def _posterior(values, columns: int, name: str, frames: int | None = None) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[1] != columns:
        raise ValueError(f'{name} must have shape [frames, {columns}].')
    if frames is not None and array.shape[0] != frames:
        raise ValueError(f'{name} must have the same frame count as chord probabilities.')
    if array.dtype.kind not in ('f', 'i', 'u'):
        raise ValueError(f'{name} must contain real numbers.')
    array = array.astype(np.float64, copy=False)
    if not np.all(np.isfinite(array)) or np.any(array < 0):
        raise ValueError(f'{name} must contain finite, nonnegative probabilities.')
    totals = np.sum(array, axis=1)
    if not np.all(np.abs(totals - 1) <= .001):
        raise ValueError(f'Each {name} row must sum to one.')
    # Remove only softmax floating point drift; never mutate callers' arrays.
    return array / totals[:, None]


def grouped_candidates(probabilities, labels: Sequence[str], bass_probabilities=None):
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
