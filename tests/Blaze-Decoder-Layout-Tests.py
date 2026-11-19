"""Bounded score/partition packing must preserve numerical and musical paths."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from music_studio.structured import observation_scores, sequence_decode


class DecoderLayoutTests(unittest.TestCase):
    def test_packed_scores_preserve_original_arithmetic_for_quiet_tied_and_normal_inputs(self):
        rng=np.random.default_rng(191)
        widths=(73,13,4,4,3,3)
        components=np.stack([rng.integers(width,size=1381) for width in widths],axis=1)
        columns=rng.integers(97,size=1381)
        frames=np.arange(131)//4
        for dtype in (np.float32,np.float64):
            for case in ('normal','quiet','ties'):
                priors=rng.uniform(0,1,(33,97)).astype(dtype)
                heads=[rng.uniform(0,1,(131,width)).astype(dtype) for width in widths]
                if case=='quiet':
                    priors[:]=0
                    for head in heads:head[:]=0
                elif case=='ties':
                    priors[:]=.5
                    for head in heads:head[:]=.5
                saved=[array.copy() for array in (priors,*heads)]
                for start,end in ((0,1),(0,128),(128,131)):
                    expected=1.2*np.log(np.maximum(priors[frames[start:end]][:,columns],1e-7))
                    for k,head in enumerate(heads):
                        expected+=(1.0 if k==0 else .65)*np.log(np.maximum(head[start:end,components[:,k]],1e-7))
                    actual=observation_scores(priors,columns,frames,heads,components,start,end)
                    self.assertEqual(actual.dtype,expected.dtype)
                    self.assertEqual(actual.tobytes(),expected.tobytes())
                for actual,original in zip((priors,*heads),saved):
                    self.assertEqual(actual.tobytes(),original.tobytes())

    def test_bounded_partitions_match_original_indices_and_paths_at_ties_and_partial_blocks(self):
        rng=np.random.default_rng(192)
        for dtype in (np.float32,np.float64):
            for width in (1,3,19,20,21,1381):
                for case in ('normal','ties','silent','near_ties'):
                    with self.subTest(dtype=dtype,width=width,case=case):
                        rows=rng.uniform(-20,0,(133,width)).astype(dtype)
                        if case=='ties':rows[:]=-.5
                        elif case=='silent':rows[:]=-1000;rows[:,0]=0
                        elif case=='near_ties':
                            rows[:]=rng.choice([dtype(.5),np.nextafter(dtype(.5),dtype(1))],size=rows.shape)
                        original=rows.copy()
                        for values in (rows,np.asfortranarray(rows)):
                            penalties=rng.choice([0.,1.8,2.8],len(values)).astype(np.float32)
                            def selected():
                                for start in range(0,len(values),128):
                                    block=values[start:start+128]
                                    tops=np.argpartition(block,-min(20,width),axis=1)[:,-20:].copy()
                                    expected=np.stack([np.argpartition(row,-min(20,width))[-20:] for row in block])
                                    self.assertEqual(tops.tobytes(),expected.tobytes())
                                    yield from zip(block,tops)
                            np.testing.assert_array_equal(sequence_decode(selected(),penalties,preselected=True),
                                                          sequence_decode(values,penalties))
                        self.assertEqual(rows.tobytes(),original.tobytes())

    def test_empty_and_cancelled_preselected_decode_keep_original_behavior(self):
        self.assertEqual(sequence_decode([],[],preselected=True).size,0)
        def cancelled():raise RuntimeError('cancel')
        with self.assertRaisesRegex(RuntimeError,'cancel'):
            sequence_decode(iter([(np.zeros(3),np.arange(3))]),[2.8],check=cancelled,preselected=True)


if __name__=='__main__':
    unittest.main()
