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


from dual_pair_buffer import build_dual_pair_buffers, DualPairResult


def _ramp(n):
    return np.arange(n, dtype=float)


class TestBuildDualPair(unittest.TestCase):
    def test_equal_periods_identity(self):
        u0, v0 = _ramp(100), _ramp(100) + 1
        u1, v1 = _ramp(100) + 2, _ramp(100) + 3
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.1)
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 100)
        self.assertEqual(r.ticks, (1, 1))
        self.assertAlmostEqual(r.frequency, 10.0)
        self.assertAlmostEqual(r.sample_rate, 1000.0)
        np.testing.assert_array_equal(r.channels[0], u0)
        np.testing.assert_array_equal(r.channels[2], u1)

    def test_channel_order_is_u0_v0_u1_v1(self):
        u0, v0 = _ramp(10), _ramp(10) + 100
        u1, v1 = _ramp(10) + 200, _ramp(10) + 300
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.1)
        np.testing.assert_array_equal(r.channels[0], u0)
        np.testing.assert_array_equal(r.channels[1], v0)
        np.testing.assert_array_equal(r.channels[2], u1)
        np.testing.assert_array_equal(r.channels[3], v1)

    def test_2x_ratio_pair1_slower(self):
        u0, v0 = _ramp(100), _ramp(100)
        u1, v1 = _ramp(100), _ramp(100)
        r = build_dual_pair_buffers(u0, v0, 0.1, u1, v1, 0.2)
        self.assertTrue(r.ok)
        self.assertEqual(r.ticks, (1, 2))
        self.assertEqual(r.num_points, 200)
        self.assertAlmostEqual(r.frequency, 5.0)
        self.assertAlmostEqual(r.sample_rate, 1000.0)
        np.testing.assert_array_equal(r.channels[0], np.tile(u0, 2))
        np.testing.assert_array_equal(r.channels[2], zoh_resample(u1, 200))

    def test_2x_ratio_pair0_slower_symmetric(self):
        u0, v0 = _ramp(100), _ramp(100)
        u1, v1 = _ramp(100), _ramp(100)
        r = build_dual_pair_buffers(u0, v0, 0.2, u1, v1, 0.1)
        self.assertEqual(r.ticks, (2, 1))
        self.assertEqual(r.num_points, 200)
        np.testing.assert_array_equal(r.channels[2], np.tile(u1, 2))
        np.testing.assert_array_equal(r.channels[0], zoh_resample(u0, 200))

    def test_3x_ratio(self):
        u0 = _ramp(50)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.3)
        self.assertEqual(r.ticks, (1, 3))
        self.assertEqual(r.num_points, 150)
        self.assertAlmostEqual(r.frequency, 1.0 / 0.3)
        self.assertAlmostEqual(r.sample_rate, 500.0)

    def test_non_integer_ratio_rounds_half_up(self):
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.15)  # 1.5 -> 2
        self.assertEqual(r.ticks, (1, 2))
        self.assertAlmostEqual(r.eff_periods[1], 0.2)


if __name__ == "__main__":
    unittest.main()
