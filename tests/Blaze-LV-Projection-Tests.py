"""Sparse CQT batching must preserve the original complex64 reductions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from music_studio import lv_frontend as lv


def reference_project(filters, spectrum):
    output = np.empty((len(filters), spectrum.shape[1]), np.complex64)
    for row, coefficients in enumerate(filters):
        indices = np.flatnonzero(coefficients)
        for start in range(0, spectrum.shape[1], 512):
            output[row, start:start + 512] = np.sum(
                coefficients[indices, None] * spectrum[indices, start:start + 512],
                axis=0, dtype=np.complex64)
    return output


def diagnose_reference(filters, spectrum):
    import hashlib
    values = [reference_project(filters, spectrum) for _ in range(8)]
    hashes = {hashlib.sha256(value.tobytes()).hexdigest() for value in values}
    error = max(float(np.max(np.abs(value-values[0]), initial=0)) for value in values)
    print({'reference_repeat_hashes': len(hashes), 'reference_self_max_error': error,
           'shape': spectrum.shape}, flush=True)


class ProjectionTests(unittest.TestCase):
    def test_original_filters_and_partial_blocks_are_bit_identical(self):
        frontend = object.__new__(lv.PortableLVFrontend)
        frontend._filter_cache = {}
        rng = np.random.default_rng(196)
        for tuning in (-.5, 0., .49):
            pseudo, nfft, full, _, _ = frontend._filters(tuning)
            for filters, fft in [(pseudo, nfft), *full]:
                groups = lv._projection_rows(filters)
                for frames in (0, 1, 7, 255, 256, 257, 511, 512, 513):
                    complex_values = (rng.normal(size=(fft // 2 + 1, frames * 2)) +
                                      1j * rng.normal(size=(fft // 2 + 1, frames * 2)))
                    for dtype in (np.float32, np.complex64, np.complex128):
                        source = complex_values.real if dtype == np.float32 else complex_values
                        spectrum = source.astype(dtype)[:, ::2]
                        expected = reference_project(filters, spectrum)
                        actual = lv._project(filters, spectrum, groups)
                        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_empty_dense_and_equal_width_rows_preserve_reduction_order(self):
        rng = np.random.default_rng(52)
        filters = (rng.normal(size=(20, 513)) + 1j * rng.normal(size=(20, 513))).astype(np.complex64)
        filters[:2] = 0
        filters[2:10, 30:] = 0
        spectrum = (rng.normal(size=(513, 513)) + 1j * rng.normal(size=(513, 513))).astype(np.complex64)
        self.assertEqual(lv._project(filters, spectrum).tobytes(), reference_project(filters, spectrum).tobytes())

    def test_response_honors_cancellation_at_block_boundary(self):
        calls = []
        def cancel():
            calls.append(True)
            if len(calls) == 2:
                raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            lv._response(np.ones(512 * 300, np.float32), np.ones((8, 513), np.complex64),
                         1024, 512, np.ones(1024), check=cancel)
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
