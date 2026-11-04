import unittest
import math
from touchpad_tablet.filter import OneEuroFilter, LowPassFilter, CoordinateSmoother, PseudoPressureCalculator

class TestFilter(unittest.TestCase):
    def test_low_pass_filter(self):
        lpf = LowPassFilter(alpha=0.5)
        v1 = lpf.filter(10.0)
        self.assertEqual(v1, 10.0)
        v2 = lpf.filter(20.0)
        self.assertEqual(v2, 15.0)

    def test_one_euro_filter(self):
        oef = OneEuroFilter(min_cutoff=0.2, beta=0.01)
        val = oef.filter(100.0, timestamp=1.0)
        self.assertEqual(val, 100.0)
        val2 = oef.filter(105.0, timestamp=1.01)
        self.assertTrue(100.0 < val2 < 105.0)

    def test_coordinate_smoother(self):
        smoother = CoordinateSmoother(smoothing=0.5, use_one_euro=True, deadzone=2.0)
        x1, y1 = smoother.filter(100.0, 200.0, timestamp=1.0)
        self.assertEqual(x1, 100.0)
        self.assertEqual(y1, 200.0)

        # Large movement exceeds deadzone -> updates position smoothly
        x2, y2 = smoother.filter(120.0, 220.0, timestamp=1.02)
        self.assertTrue(100.0 < x2 < 120.0)
        self.assertTrue(200.0 < y2 < 220.0)

        # Micro-fluctuation below deadzone -> ignored to prevent jitter
        x3, y3 = smoother.filter(x2 + 0.1, y2 + 0.1, timestamp=1.03)
        self.assertEqual(x3, x2)
        self.assertEqual(y3, y2)

    def test_pseudo_pressure_velocity(self):
        calc = PseudoPressureCalculator(min_pressure=500, max_pressure=4000, curve_type="velocity")
        p1 = calc.compute(100.0, 100.0, timestamp=1.0)
        self.assertTrue(500 <= p1 <= 4000)

        # Slow movement -> should stay relatively high
        p_slow = calc.compute(101.0, 101.0, timestamp=1.1)
        self.assertGreater(p_slow, 2000)

        # Fast flick -> should reduce pressure
        p_fast = calc.compute(2000.0, 2000.0, timestamp=1.11)
        self.assertLess(p_fast, p_slow)

if __name__ == "__main__":
    unittest.main()
