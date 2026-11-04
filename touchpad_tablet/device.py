"""Touchpad discovery, hardware capability probing, and display resolution detection."""

import os
import glob
import fcntl
import ctypes
import subprocess
import json
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple

from .utils import (
    EVIOCGNAME,
    EVIOCGBIT,
    EVIOCGPROP,
    EVIOCGABS,
    EV_ABS,
    EV_KEY,
    BTN_TOOL_FINGER,
    BTN_TOUCH,
    INPUT_PROP_POINTER,
    INPUT_PROP_BUTTONPAD,
    ABS_X,
    ABS_Y,
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    input_absinfo,
    test_bit,
)


@dataclass
class AxisInfo:
    code: int
    minimum: int
    maximum: int
    fuzz: int
    flat: int
    resolution: int  # units per mm

    @property
    def range(self) -> int:
        return self.maximum - self.minimum


@dataclass
class TouchpadInfo:
    path: str
    name: str
    axis_x: AxisInfo
    axis_y: AxisInfo
    has_multitouch: bool
    is_buttonpad: bool

    @property
    def width_mm(self) -> float:
        if self.axis_x.resolution > 0:
            return self.axis_x.range / self.axis_x.resolution
        return 0.0

    @property
    def height_mm(self) -> float:
        if self.axis_y.resolution > 0:
            return self.axis_y.range / self.axis_y.resolution
        return 0.0

    @property
    def aspect_ratio(self) -> float:
        if self.axis_y.range > 0:
            return self.axis_x.range / self.axis_y.range
        return 1.0


def probe_axis(fd: int, axis_code: int) -> Optional[AxisInfo]:
    """Queries min, max, and resolution for a specific ABS axis."""
    abs_data = input_absinfo()
    try:
        fcntl.ioctl(fd, EVIOCGABS(axis_code), abs_data)
        return AxisInfo(
            code=axis_code,
            minimum=abs_data.minimum,
            maximum=abs_data.maximum,
            fuzz=abs_data.fuzz,
            flat=abs_data.flat,
            resolution=abs_data.resolution,
        )
    except OSError:
        return None


def probe_device(path: str) -> Optional[TouchpadInfo]:
    """Inspects a single /dev/input/event* path to determine if it is a touchpad."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None

    try:
        # 1. Read Name
        name_buf = ctypes.create_string_buffer(256)
        fcntl.ioctl(fd, EVIOCGNAME(256), name_buf)
        name = name_buf.value.decode("utf-8", "ignore").strip()

        # 2. Read Event Types (EV bits)
        ev_bits = ctypes.create_string_buffer(8)
        fcntl.ioctl(fd, EVIOCGBIT(0, 8), ev_bits)
        has_abs = test_bit(ev_bits.raw, EV_ABS)
        has_key = test_bit(ev_bits.raw, EV_KEY)

        if not (has_abs and has_key):
            return None

        # 3. Read Key bits (Look for BTN_TOOL_FINGER or BTN_TOUCH)
        key_bits = ctypes.create_string_buffer(96)
        fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, 96), key_bits)
        has_finger = test_bit(key_bits.raw, BTN_TOOL_FINGER)
        has_touch = test_bit(key_bits.raw, BTN_TOUCH)

        # 4. Read Properties
        prop_bits = ctypes.create_string_buffer(8)
        is_buttonpad = False
        try:
            fcntl.ioctl(fd, EVIOCGPROP(8), prop_bits)
            is_buttonpad = test_bit(prop_bits.raw, INPUT_PROP_BUTTONPAD)
        except OSError:
            pass

        # Heuristic: Must support ABS events and finger/touch tool or have touchpad in name
        is_touchpad = (has_finger or "touchpad" in name.lower() or "trackpad" in name.lower())
        if not is_touchpad:
            return None

        # 5. Query X and Y Axes (Prefer ABS_MT_POSITION_X/Y if available)
        axis_x = probe_axis(fd, ABS_MT_POSITION_X) or probe_axis(fd, ABS_X)
        axis_y = probe_axis(fd, ABS_MT_POSITION_Y) or probe_axis(fd, ABS_Y)

        if not axis_x or not axis_y or axis_x.range <= 0 or axis_y.range <= 0:
            return None

        has_mt = probe_axis(fd, ABS_MT_POSITION_X) is not None

        return TouchpadInfo(
            path=path,
            name=name,
            axis_x=axis_x,
            axis_y=axis_y,
            has_multitouch=has_mt,
            is_buttonpad=is_buttonpad,
        )
    finally:
        os.close(fd)


def find_touchpads() -> List[TouchpadInfo]:
    """Scans all /dev/input/event* nodes and returns detected touchpads."""
    touchpads = []
    for path in sorted(glob.glob("/dev/input/event*")):
        info = probe_device(path)
        if info:
            touchpads.append(info)
    return touchpads


def get_touchpad(device_path: Optional[str] = None) -> TouchpadInfo:
    """Finds the requested touchpad or auto-detects the primary laptop touchpad."""
    if device_path:
        info = probe_device(device_path)
        if not info:
            raise RuntimeError(f"Device at {device_path} is not a valid touchpad or is inaccessible.")
        return info

    touchpads = find_touchpads()
    if not touchpads:
        raise RuntimeError("No laptop touchpad detected in /dev/input/event*.")
    return touchpads[0]


def detect_display_resolution() -> Tuple[int, int]:
    """Detects active display resolution under Hyprland, Sway, generic Wayland, or X11."""
    # 1. Hyprland compositor
    try:
        res = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            if data and isinstance(data, list):
                # Pick focused monitor or first monitor
                focused = next((m for m in data if m.get("focused")), data[0])
                w, h = int(focused["width"]), int(focused["height"])
                if w > 0 and h > 0:
                    return w, h
    except Exception:
        pass

    # 2. wlroots / wlr-randr
    try:
        res = subprocess.run(["wlr-randr"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            m = re.search(r"(\d+)x(\d+)\s+px", res.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    # 3. X11 / xrandr
    try:
        res = subprocess.run(["xrandr"], capture_output=True, text=True, timeout=1)
        if res.returncode == 0:
            m = re.search(r"current\s+(\d+)\s+x\s+(\d+)", res.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass

    # Fallback default
    return 1920, 1080
