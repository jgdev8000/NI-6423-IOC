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

    def test_empty_pattern_returns_error(self):
        r = build_dual_pair_buffers(_ramp(0), _ramp(0), 0.1, _ramp(10), _ramp(10), 0.1)
        self.assertFalse(r.ok)
        self.assertIn("empty", r.error)
        self.assertEqual(r.channels, [])


class TestBuildDualPairEdges(unittest.TestCase):
    def test_reject_when_exceeds_max_points(self):
        u0 = _ramp(4000)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.3)  # L = 3*4000
        self.assertFalse(r.ok)
        self.assertIn("12000", r.error)
        self.assertIn("10000", r.error)
        self.assertEqual(r.channels, [])

    def test_fast_loop_allowed_above_hw_min(self):
        # 1000 pts at 250 kS/s -> 4 ms hardware minimum; 4 ms must be allowed.
        u0 = _ramp(1000)
        r = build_dual_pair_buffers(u0, u0, 0.004, u0, u0, 0.004)
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.base_period, 0.004)
        self.assertAlmostEqual(r.sample_rate, 250000.0)
        self.assertNotIn("raised", r.info)

    def test_clamp_below_hardware_min(self):
        # 100 pts -> hw min 100/250000 = 0.4 ms; a faster request is raised.
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.0001, u0, u0, 0.0001)
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.base_period, 100 / 250000.0)
        self.assertLessEqual(r.sample_rate, 250000.0 + 1e-6)
        self.assertIn("raised to", r.info)

    def test_no_artificial_01s_floor(self):
        # 100 pts at 10 ms used to be clamped to 0.1 s; now it must pass through.
        u0 = _ramp(100)
        r = build_dual_pair_buffers(u0, u0, 0.01, u0, u0, 0.01)
        self.assertAlmostEqual(r.base_period, 0.01)
        self.assertNotIn("raised", r.info)

    def test_max_ao_rate_override(self):
        # max_ao_rate is configurable; 1000 pts @ 1 MS/s -> 1 ms min.
        u0 = _ramp(1000)
        r = build_dual_pair_buffers(u0, u0, 0.001, u0, u0, 0.001, max_ao_rate=1_000_000.0)
        self.assertTrue(r.ok)
        self.assertAlmostEqual(r.base_period, 0.001)

    def test_equal_period_unequal_points_resamples_and_warns(self):
        u0 = _ramp(100)
        u1 = _ramp(50)
        r = build_dual_pair_buffers(u0, u0, 0.1, u1, u1, 0.1)
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 100)            # S = pair0 length
        self.assertEqual(len(r.channels[2]), 100)
        self.assertIn("AO2/3 resampled 50->100", r.info)
        np.testing.assert_array_equal(r.channels[2], zoh_resample(u1, 100))

    def test_at_limit_is_accepted(self):
        u0 = _ramp(5000)
        r = build_dual_pair_buffers(u0, u0, 0.1, u0, u0, 0.2)  # L = 2*5000
        self.assertTrue(r.ok)
        self.assertEqual(r.num_points, 10000)


if __name__ == "__main__":
    unittest.main()
