"""Sparse CQT batching must preserve the original complex64 reductions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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


def assert_reference_output(test, filters, spectrum, actual, expected):
    if actual.tobytes() == expected.tobytes():
        return
    # NumPy's reduction kernel may depend on the temporary's address. Compare
    # both original computations at each identical alignment instead of drawing
    # a probabilistic min/max envelope from unrelated allocator samples. Copies
    # preserve every input bit; the reduction itself is still NumPy's original.
    original_sum = np.sum
    for alignment in range(0, 64, 8):
        def aligned_sum(value, *args, **kwargs):
            test.assertTrue(value.flags.c_contiguous or value.flags.f_contiguous)
            storage = np.empty(value.nbytes + 64, dtype=np.uint8)
            offset = (alignment - storage.ctypes.data) % 64
            controlled = np.ndarray(value.shape, dtype=value.dtype, buffer=storage,
                                    offset=offset, order='F' if value.flags.f_contiguous else 'C')
            controlled[...] = value
            return original_sum(controlled, *args, **kwargs)
        with patch.object(np, 'sum', side_effect=aligned_sum):
            reference = reference_project(filters, spectrum)
            candidate = lv._project(filters, spectrum)
        test.assertEqual(candidate.tobytes(), reference.tobytes(),
                         f'Projection differs with controlled {alignment}-byte alignment')
    print({'controlled_reference_alignments': 8, 'exact_match': True,
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
                        assert_reference_output(self, filters, spectrum, actual, expected)

    def test_empty_dense_and_equal_width_rows_preserve_reduction_order(self):
        rng = np.random.default_rng(52)
        filters = (rng.normal(size=(20, 513)) + 1j * rng.normal(size=(20, 513))).astype(np.complex64)
        filters[:2] = 0
        filters[2:10, 30:] = 0
        spectrum = (rng.normal(size=(513, 513)) + 1j * rng.normal(size=(513, 513))).astype(np.complex64)
        assert_reference_output(self, filters, spectrum, lv._project(filters, spectrum),
                                reference_project(filters, spectrum))

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
