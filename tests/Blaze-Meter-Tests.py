"""Focused checks for timestamp-based automatic bar grouping."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_studio.meter import estimate_meter


def recording(counts, pulse=.5, offset=0):
    beats, downbeats = [], [offset]
    position = offset
    for count in counts:
        for _ in range(count):
            beats.append(position)
            position += pulse
        downbeats.append(position)
    beats.append(position)
    return beats, downbeats, position + .1


for count in range(2, 13):
    beats, downbeats, duration = recording([count] * 4)
    output = estimate_meter(beats, downbeats, duration)
    assert output['beats_per_bar'] == count
    assert output['denominator'] is None
    assert output['label'] == f'{count} beats/bar'
    assert len(output['bars']) == 4
    assert output['confidence'] == 1
    assert output['bars'][0]['start'] == 0
    assert output['bars'][-1]['end'] == downbeats[-1]
    assert all(len(bar['beats']) == count for bar in output['bars'])
    json.dumps(output, allow_nan=False)

# Two complete bars are insufficient; recording length never invents a last bar.
beats, downbeats, duration = recording([4, 4])
assert estimate_meter(beats, downbeats, duration)['bars'] == []
beats, downbeats, duration = recording([4, 4, 4])
output = estimate_meter(beats + [duration + .4], downbeats, duration + 1)
assert len(output['bars']) == 3
assert output['bars'][-1]['end'] == 6

# Preserve pickup/lead-in timing and original irregular, slowly changing pulses.
beats, downbeats, duration = recording([3] * 3, offset=.7)
output = estimate_meter([0, .3] + beats, downbeats, duration)
assert output['bars'][0]['start'] == .7
assert output['bars'][0]['beats'] == [.7, 1.2, 1.7]
beats = [0, .4, .82, 1.26, 1.72, 2.2, 2.7, 3.22, 3.76, 4.32, 4.9, 5.5, 6.12]
downbeats = [beats[index] for index in (0, 4, 8, 12)]
output = estimate_meter(beats, downbeats, 6.5)
assert output['beats_per_bar'] == 4
assert output['bars'][1]['start'] == 1.72
assert output['bars'][1]['end'] == 3.76
assert output['bars'][1]['beats'] == beats[4:8]

# Separate reliable variable-meter runs; short changes remain ungrouped.
beats, downbeats, duration = recording([3] * 3 + [4] * 3)
output = estimate_meter(beats, downbeats, duration)
assert output['label'] == 'Variable meter'
assert output['beats_per_bar'] is None
assert [bar['beats_per_bar'] for bar in output['bars']] == [3] * 3 + [4] * 3
assert output['bars'][3]['start'] == downbeats[3]
beats, downbeats, duration = recording([3, 4, 3, 4, 3, 4])
assert estimate_meter(beats, downbeats, duration)['label'] == 'Unknown'

# An unmatched boundary interrupts a run; it is not moved to a nearby beat.
beats, downbeats, duration = recording([4] * 3)
assert estimate_meter(beats, [0, 2.2, 4, 6], duration)['bars'] == []
beats, downbeats, duration = recording([4] * 7)
downbeats[3] += .2
output = estimate_meter(beats, downbeats, duration)
assert len(output['bars']) == 3
assert output['bars'][0]['start'] == 8
assert output['confidence'] < 1

# A missing beat/doubled pulse or random timing cannot produce confident bars.
beats, downbeats, duration = recording([4] * 3)
assert estimate_meter([value for value in beats if value != .5], downbeats, duration)['bars'] == []
assert estimate_meter(sorted(beats + [.25]), downbeats, duration)['bars'] == []
random_beats = [0, .2, 1.2, 1.4, 2.4, 2.6, 3.6, 3.8, 4.8, 5, 6, 6.2, 7.2]
assert estimate_meter(random_beats, [0, 2.4, 4.8, 7.2], 8)['bars'] == []
for pulse in (.05, 4):
    beats, downbeats, duration = recording([4] * 3, pulse=pulse)
    assert estimate_meter(beats, downbeats, duration)['bars'] == []

# Invalid values are discarded without introducing NaN into JSON. Ordering errors
# are rejected instead of silently sorting inconsistent model output.
beats, downbeats, duration = recording([4] * 3)
dirty_beats = [-1, False, float('nan'), '0', 0, 0, *beats[1:], float('inf'), duration + 1]
dirty_downbeats = [None, -1, 0, 0, *downbeats[1:], float('nan'), duration + 1]
output = estimate_meter(dirty_beats, dirty_downbeats, duration)
assert output['beats_per_bar'] == 4
json.dumps(output, allow_nan=False)
assert estimate_meter(list(reversed(beats)), downbeats, duration)['bars'] == []
assert estimate_meter(beats, list(reversed(downbeats)), duration)['bars'] == []
for invalid_duration in (0, -1, None, True, '10', float('nan'), float('inf')):
    assert estimate_meter(beats, downbeats, invalid_duration)['label'] == 'Unknown'
for invalid in (None, '', {}, [], [0]):
    assert estimate_meter(invalid, downbeats, duration)['bars'] == []
    assert estimate_meter(beats, invalid, duration)['bars'] == []
assert estimate_meter([], [], 30)['label'] == 'Unknown'

print('Meter: reliable 2-12 pulse bars, variable/irregular timing, lead-in, partial final, silence, invalid values and ambiguous boundaries PASS')
