import unittest
from touchpad_tablet.device import find_touchpads, detect_display_resolution

class TestDevice(unittest.TestCase):
    def test_find_touchpads(self):
        touchpads = find_touchpads()
        self.assertGreaterEqual(len(touchpads), 1)
        primary = touchpads[0]
        self.assertTrue(primary.path.startswith("/dev/input/event"))
        self.assertGreater(primary.axis_x.maximum, 0)
        self.assertGreater(primary.axis_y.maximum, 0)

    def test_detect_resolution(self):
        w, h = detect_display_resolution()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

if __name__ == "__main__":
    unittest.main()
