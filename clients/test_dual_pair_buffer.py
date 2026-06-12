# clients/test_dual_pair_buffer.py
import unittest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_pair_buffer import zoh_resample


class TestZohResample(unittest.TestCase):
    def test_identity_when_same_length(self):
        a = np.array([1.0, 2.0, 3.0])
        out = zoh_resample(a, 3)
        np.testing.assert_array_equal(out, a)

    def test_upsample_holds_each_sample(self):
        out = zoh_resample([10.0, 20.0], 4)
        np.testing.assert_array_equal(out, [10.0, 10.0, 20.0, 20.0])

    def test_downsample_decimates(self):
        out = zoh_resample([1.0, 2.0, 3.0, 4.0], 2)
        np.testing.assert_array_equal(out, [1.0, 3.0])

    def test_non_integer_ratio_uses_floor_index(self):
        out = zoh_resample([0.0, 1.0, 2.0], 5)  # idx = floor(j*3/5)
        np.testing.assert_array_equal(out, [0.0, 0.0, 1.0, 1.0, 2.0])

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            zoh_resample([], 4)

    def test_nonpositive_target_raises(self):
        with self.assertRaises(ValueError):
            zoh_resample([1.0, 2.0], 0)
        with self.assertRaises(ValueError):
            zoh_resample([1.0, 2.0], -3)


if __name__ == "__main__":
    unittest.main()
