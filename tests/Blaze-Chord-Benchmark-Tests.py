"""A benchmark must distinguish score drift from changed musical results."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from benchmark_macos_chord_pipeline import compare_results


class ResultComparison(unittest.TestCase):
    def setUp(self):
        self.reference = {'duration': 2., 'beats': [.5, 1.], 'key': 'C major', 'tempo_bpm': 120.,
                          'chords': [{'start': 0., 'end': 2., 'chord': 'C:maj', 'edited': False, 'model_score': .7}]}

    def compare(self, candidate):
        encode = lambda x: json.dumps(x, sort_keys=True).encode()
        return compare_results(encode(candidate), encode(self.reference))

    def test_score_drift_is_visible_and_never_claimed_byte_exact(self):
        candidate = json.loads(json.dumps(self.reference))
        candidate['chords'][0]['model_score'] += 1e-7
        result = self.compare(candidate)
        self.assertFalse(result['exact_bytes'])
        self.assertTrue(result['timeline_and_metadata_exact'])
        self.assertTrue(result['score_availability_exact'])
        self.assertGreater(result['max_score_abs_error'], 0)

    def test_changed_chords_times_rhythm_and_metadata_are_not_ignored(self):
        for key, value in [('chord', 'F:maj'), ('end', 1.9), ('edited', True)]:
            candidate = json.loads(json.dumps(self.reference))
            candidate['chords'][0][key] = value
            self.assertFalse(self.compare(candidate)['timeline_and_metadata_exact'])
        for key, value in [('beats', [.6, 1.]), ('key', 'F major'), ('duration', 2.1), ('tempo_bpm', 121.)]:
            candidate = dict(self.reference, **{key: value})
            self.assertFalse(self.compare(candidate)['timeline_and_metadata_exact'])
        self.assertFalse(self.compare(dict(self.reference, chords=[]))['timeline_and_metadata_exact'])

    def test_missing_or_uncertain_scores_are_distinguished(self):
        for value in (None, 'missing'):
            candidate = json.loads(json.dumps(self.reference))
            if value == 'missing':
                del candidate['chords'][0]['model_score']
            else:
                candidate['chords'][0]['model_score'] = value
            self.assertFalse(self.compare(candidate)['score_availability_exact'])
        self.assertTrue(self.compare(self.reference)['exact_bytes'])


if __name__ == '__main__':
    unittest.main()
