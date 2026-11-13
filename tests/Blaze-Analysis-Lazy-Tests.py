"""Verified cache hits must not create inference sessions or trust changed assets."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from music_studio.engine import ModelBundle, waveform_peaks, Analyzer, AnalysisCancelled
from music_studio.verified_session import VerifiedSession


class LazyTests(unittest.TestCase):
    def test_vectorized_waveform_preserves_peaks_for_silence_edges_and_strided_blocks(self):
        rng = np.random.default_rng(18)
        blocks = rng.normal(size=(867, 512)).astype(np.float32)[:, ::2]
        blocks[0] = 0
        blocks[1, 0] = -3
        blocks[-1, -1] = 4
        expected = [float(np.max(np.abs(block))) for block in blocks]
        self.assertEqual(waveform_peaks(blocks), expected)
        self.assertEqual(waveform_peaks(np.empty((0, 256), dtype=np.float32)), [])

    def test_private_verified_copy_skips_second_read_but_changed_file_is_rehashed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.wav'
            path.write_bytes(b'original recording')
            analyzer = Analyzer(None, 'ffmpeg')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            analyzer.verified_input = (path, analyzer.input_stamp(path), expected)
            with patch.object(Path, 'open', side_effect=AssertionError('Redundant source read')):
                self.assertEqual(analyzer._source_digest(path), expected)
            path.write_bytes(b'replaced recording')
            self.assertEqual(analyzer._source_digest(path), hashlib.sha256(path.read_bytes()).hexdigest())
            other = Path(directory) / 'other.wav'
            other.write_bytes(b'other recording')
            self.assertEqual(analyzer._source_digest(other), hashlib.sha256(other.read_bytes()).hexdigest())
            analyzer.cancel()
            with self.assertRaises(AnalysisCancelled):
                analyzer._source_digest(path)

    def test_streamed_ensemble_matches_original_mean(self):
        from music_studio.structured import StructuredRecognizer
        rng = np.random.default_rng(81)
        raw = [[rng.normal(size=(31, width)).astype(np.float32) for width in (12, 8, 4, 3, 6, 2)] for _ in range(5)]
        votes = []
        for outputs in raw:
            probs = []
            for head in outputs:
                head = np.exp(head - head.max(axis=1, keepdims=True))
                head /= head.sum(axis=1, keepdims=True)
                probs.append(head)
            votes.append(probs)
        expected = [np.mean([vote[k] for vote in votes], axis=0) for k in range(6)]
        engine = StructuredRecognizer.__new__(StructuredRecognizer)
        engine.networks = [Mock(run=Mock(return_value=value)) for value in raw]
        actual = engine.predict_features(np.zeros((31, 252), dtype=np.float32))
        # Context weighting adds the same float32 roundoff to both paths.
        weight = np.minimum(np.minimum(np.arange(31)+1, np.arange(31,0,-1)),129)/129
        for got, want in zip(actual, expected):
            weighted = np.asarray(want * weight[:,None], dtype=np.float32)
            weighted /= weight.astype(np.float32)[:,None]
            np.testing.assert_array_equal(got, weighted)

    def test_verified_session_defers_load_reuses_and_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.onnx'
            path.write_bytes(b'verified')
            metadata = {'file': path.name, 'sha256': hashlib.sha256(b'verified').hexdigest()}
            runtime = Mock()
            session = VerifiedSession(directory, metadata, runtime, None, 100)
            runtime.session.assert_not_called()
            session.run(None, {})
            session.run(None, {})
            runtime.session.assert_called_once_with(b'verified', None, metadata['sha256'])
            session.close()
            path.write_bytes(b'replaced')
            with self.assertRaisesRegex(ValueError, 'verification'):
                session.run(None, {})
            self.assertEqual(runtime.session.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'verification'):
                VerifiedSession(directory, metadata, runtime, None, 100)

    def test_powerful_bundle_validates_every_asset_without_opening_neural_sessions(self):
        original = Path(__file__).resolve().parents[1] / 'music_studio/models'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            basic = json.loads((original / 'manifest.json').read_text())
            structured = json.loads((original / 'structured_manifest.json').read_text())
            assets = [basic['frontend'], *basic['models'].values(), structured['frontend'], *structured['models']]
            for asset in assets:
                data = asset['file'].encode()
                (root / asset['file']).write_bytes(data)
                asset['sha256'] = hashlib.sha256(data).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(basic))
            (root / 'structured_manifest.json').write_text(json.dumps(structured))
            with patch('music_studio.engine.StemRuntime') as runtime, \
                    patch('music_studio.stem_runtime.StemRuntime') as ensemble_runtime, \
                    patch('music_studio.structured.PortableLVFrontend'):
                bundle = ModelBundle(root, 'powerful')
                expected = [basic['models']['extended']['sha256'], structured['frontend']['sha256'],
                            *(asset['sha256'] for asset in structured['models'])]
                self.assertEqual(bundle.metadata['sha256'], hashlib.sha256(''.join(expected).encode()).hexdigest())
                runtime.return_value.session.assert_not_called()
                ensemble_runtime.return_value.session.assert_not_called()
                bundle.close()
                (root / structured['models'][-1]['file']).write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError, 'verification'):
                    ModelBundle(root, 'powerful')
                ensemble_runtime.return_value.session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
