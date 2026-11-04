import unittest
import tempfile
from pathlib import Path
from touchpad_tablet.config import TabletConfig

class TestConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = TabletConfig()
        self.assertEqual(cfg.start_mode, "mouse")
        self.assertEqual(cfg.aspect_ratio, "fit")
        self.assertEqual(cfg.smoothing, 0.5)
        self.assertEqual(cfg.deadzone, 2.5)
        self.assertEqual(cfg.click_action, "none")
        self.assertTrue(cfg.use_one_euro)
        self.assertEqual(cfg.pressure_min, 800)
        self.assertEqual(cfg.pressure_max, 4096)

    def test_generate_toml(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = TabletConfig(smoothing=0.6, aspect_ratio="stretch", deadzone=3.0)
            out_file = Path(tmp_dir) / "config.toml"
            cfg.save(out_file)
            self.assertTrue(out_file.exists())

            loaded = TabletConfig.load(out_file)
            self.assertEqual(loaded.smoothing, 0.6)
            self.assertEqual(loaded.deadzone, 3.0)
            self.assertEqual(loaded.aspect_ratio, "stretch")

if __name__ == "__main__":
    unittest.main()
