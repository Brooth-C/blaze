"""Conservative grouping of predicted beats and downbeats; no notation guessed."""

from bisect import bisect_left
from math import isfinite
from numbers import Real
from statistics import median


_DUPLICATE_EPSILON = 1e-6
_BOUNDARY_EPSILON = 1e-4
_MIN_PULSE_SECONDS = 0.18
_MAX_PULSE_SECONDS = 3.0
_MAX_TEMPO_RATIO = 1.6
_MIN_RUN_BARS = 3


def _timestamps(values, duration):
    """Remove invalid/duplicate values, rejecting meaningful backwards ordering."""
    if isinstance(values, (str, bytes, dict)):
        return None
    try:
        iterator = iter(values)
    except TypeError:
        return None
    cleaned = []
    for value in iterator:
        if isinstance(value, bool) or not isinstance(value, Real):
            continue
        value = float(value)
        if not isfinite(value) or value < 0 or value > duration:
            continue
        if cleaned:
            difference = value - cleaned[-1]
            if difference < -_DUPLICATE_EPSILON:
                return None
            if difference <= _DUPLICATE_EPSILON:
                continue
        cleaned.append(value)
    return cleaned


def _matching_beat(beats, downbeat):
    position = bisect_left(beats, downbeat)
    candidates = [index for index in (position - 1, position) if 0 <= index < len(beats)]
    if not candidates:
        return None
    index = min(candidates, key=lambda candidate: abs(beats[candidate] - downbeat))
    # Beat This! already aligns downbeats to beats. Allow rounding, not resnapping.
    return index if abs(beats[index] - downbeat) <= _BOUNDARY_EPSILON else None


def _ratio(first, second):
    return max(first, second) / min(first, second)


def estimate_meter(beats, downbeats, duration):
    """Return reliable bar runs using only the supplied predicted timestamps.

    At least three consecutive complete bars must agree on their pulse count.
    Unmatched boundaries, missing/doubled pulses and implausible tempo jumps break
    runs. The confidence is the fraction of supplied boundary intervals retained,
    not a calibrated model probability. A pulse count cannot identify a notation
    denominator or distinguish, for example, two quarter notes from two dotted
    quarter notes; ``denominator`` therefore always remains ``None``.
    """
    unknown = {
        "beats_per_bar": None,
        "denominator": None,
        "label": "Unknown",
        "bars": [],
        "confidence_kind": "bar_consistency",
        "confidence": None,
    }
    if isinstance(duration, bool) or not isinstance(duration, Real):
        return unknown
    duration = float(duration)
    if not isfinite(duration) or duration <= 0:
        return unknown
    beats = _timestamps(beats, duration)
    downbeats = _timestamps(downbeats, duration)
    if beats is None or downbeats is None or len(beats) < 3 or len(downbeats) < 4:
        return unknown

    boundaries = [(_matching_beat(beats, time), time) for time in downbeats]
    # Different near-duplicate downbeat predictions can match the same beat.
    unique = []
    for boundary in boundaries:
        if unique and boundary[0] is not None and boundary[0] == unique[-1][0]:
            continue
        unique.append(boundary)
    if len(unique) < 4:
        return unknown

    intervals = []
    for (first, start), (following, end) in zip(unique, unique[1:]):
        candidate = None
        if first is not None and following is not None and 2 <= following - first <= 12:
            pulses = [beats[index + 1] - beats[index] for index in range(first, following)]
            typical = median(pulses)
            plausible = all(_MIN_PULSE_SECONDS <= pulse <= _MAX_PULSE_SECONDS for pulse in pulses)
            regular = all(1 / _MAX_TEMPO_RATIO <= pulse / typical <= _MAX_TEMPO_RATIO for pulse in pulses)
            continuous = all(_ratio(left, right) <= _MAX_TEMPO_RATIO for left, right in zip(pulses, pulses[1:]))
            if plausible and regular and continuous:
                candidate = ({
                    "start": start,
                    "end": end,
                    "beats": beats[first:following],
                    "beats_per_bar": following - first,
                }, typical)
        intervals.append(candidate)

    accepted = []
    run = []

    def finish():
        if len(run) >= _MIN_RUN_BARS:
            accepted.extend(item[0] for item in run)
        run.clear()

    for candidate in intervals:
        if candidate is None:
            finish()
            continue
        if run and (
            candidate[0]["beats_per_bar"] != run[-1][0]["beats_per_bar"]
            or _ratio(candidate[1], run[-1][1]) > _MAX_TEMPO_RATIO
        ):
            finish()
        run.append(candidate)
    finish()
    if not accepted:
        return unknown
    counts = {bar["beats_per_bar"] for bar in accepted}
    count = next(iter(counts)) if len(counts) == 1 else None
    return {
        "beats_per_bar": count,
        "denominator": None,
        "label": f"{count} beats/bar" if count is not None else "Variable meter",
        "bars": accepted,
        "confidence_kind": "bar_consistency",
        "confidence": round(len(accepted) / len(intervals), 6),
    }
