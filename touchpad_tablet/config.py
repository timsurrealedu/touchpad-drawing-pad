"""Configuration models and TOML file loader."""

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


DEFAULT_CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "touchpad-tablet" / "config.toml"


@dataclass
class TabletConfig:
    device: Optional[str] = None
    start_mode: str = "tablet"  # "tablet" or "mouse"
    aspect_ratio: str = "fit"  # "fit", "stretch"
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    smoothing: float = 0.35  # 0.0 to 1.0 (0.0 = raw, 1.0 = heavy smoothing)
    use_one_euro: bool = True
    pressure_min: int = 800
    pressure_max: int = 4096
    pressure_curve: str = "velocity"  # "velocity", "constant"
    click_action: str = "stylus"  # "stylus" (BTN_STYLUS), "touch", "none"
    notifications: bool = True

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TabletConfig":
        cfg_file = path or DEFAULT_CONFIG_PATH
        if not cfg_file.exists() or tomllib is None:
            return cls()

        try:
            with open(cfg_file, "rb") as f:
                data = tomllib.load(f)
            tablet_data = data.get("tablet", {})
            return cls(
                device=tablet_data.get("device"),
                start_mode=tablet_data.get("start_mode", "tablet"),
                aspect_ratio=tablet_data.get("aspect_ratio", "fit"),
                screen_width=tablet_data.get("screen_width"),
                screen_height=tablet_data.get("screen_height"),
                smoothing=float(tablet_data.get("smoothing", 0.35)),
                use_one_euro=bool(tablet_data.get("use_one_euro", True)),
                pressure_min=int(tablet_data.get("pressure_min", 800)),
                pressure_max=int(tablet_data.get("pressure_max", 4096)),
                pressure_curve=tablet_data.get("pressure_curve", "velocity"),
                click_action=tablet_data.get("click_action", "stylus"),
                notifications=bool(tablet_data.get("notifications", True)),
            )
        except Exception:
            return cls()

    def generate_toml(self) -> str:
        dev_str = f'"{self.device}"' if self.device else "# auto-detect"
        sw_str = str(self.screen_width) if self.screen_width else "# auto-detect"
        sh_str = str(self.screen_height) if self.screen_height else "# auto-detect"

        return f"""# Touchpad Drawing Pad Configuration File
# Location: ~/.config/touchpad-tablet/config.toml

[tablet]
# Specific touchpad event node (leave commented to auto-detect laptop touchpad)
# device = {dev_str}

# Initial mode on daemon startup ("tablet" or "mouse")
start_mode = "{self.start_mode}"

# Aspect ratio correction ("fit" = maintain screen aspect ratio, "stretch" = 1:1 surface mapping)
aspect_ratio = "{self.aspect_ratio}"

# Target screen resolution in pixels (leave commented to auto-detect via Hyprland/xrandr)
# screen_width = {sw_str}
# screen_height = {sh_str}

# Coordinate smoothing factor (0.0 = raw hardware events, 0.35 = balanced, 0.8 = heavy smoothing)
smoothing = {self.smoothing}

# Use One-Euro adaptive filter (recommended, eliminates jitter at low speeds while keeping zero latency at high speeds)
use_one_euro = {"true" if self.use_one_euro else "false"}

# Pseudo-pressure dynamics
pressure_min = {self.pressure_min}
pressure_max = {self.pressure_max}
pressure_curve = "{self.pressure_curve}" # "velocity" or "constant"

# Physical clickpad press action ("stylus" = trigger BTN_STYLUS for palette/right-click, "touch", "none")
click_action = "{self.click_action}"

# Desktop notifications on mode toggling
notifications = {"true" if self.notifications else "false"}
"""

    def save(self, path: Optional[Path] = None) -> Path:
        cfg_file = path or DEFAULT_CONFIG_PATH
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(self.generate_toml(), encoding="utf-8")
        return cfg_file
