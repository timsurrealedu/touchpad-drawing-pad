"""Virtual graphics digitizer tablet creation and event injection via /dev/uinput."""

import os
import fcntl
import ctypes
import time
from typing import Optional

from .utils import (
    EV_SYN,
    EV_KEY,
    EV_ABS,
    SYN_REPORT,
    BTN_TOOL_PEN,
    BTN_TOUCH,
    BTN_STYLUS,
    BTN_STYLUS2,
    ABS_X,
    ABS_Y,
    ABS_PRESSURE,
    INPUT_PROP_DIRECT,
    BUS_USB,
    UI_DEV_CREATE,
    UI_DEV_DESTROY,
    UI_DEV_SETUP,
    UI_ABS_SETUP,
    UI_SET_EVBIT,
    UI_SET_KEYBIT,
    UI_SET_ABSBIT,
    UI_SET_PROPBIT,
    input_event,
    uinput_setup,
    uinput_abs_setup,
)


class UInputTablet:
    """Manages an emulated graphics tablet exposed directly to the OS kernel via /dev/uinput."""

    def __init__(
        self,
        max_x: int,
        max_y: int,
        max_pressure: int = 4096,
        resolution_x: int = 24,
        resolution_y: int = 24,
        device_name: str = "Touchpad Virtual Graphics Tablet",
        vendor_id: int = 0x056a,  # Wacom Vendor ID
        product_id: int = 0x0357,
    ):
        self.max_x = max_x
        self.max_y = max_y
        self.max_pressure = max_pressure
        self.resolution_x = resolution_x
        self.resolution_y = resolution_y
        self.device_name = device_name
        self.vendor_id = vendor_id
        self.product_id = product_id

        self.fd: Optional[int] = None
        self._pen_in_proximity = False
        self._pen_touching = False
        self._stylus_active = False

        self._create_device()

    def _setup_abs(self, code: int, max_val: int, resolution: int) -> None:
        abs_setup = uinput_abs_setup()
        abs_setup.code = code
        abs_setup.absinfo.value = 0
        abs_setup.absinfo.minimum = 0
        abs_setup.absinfo.maximum = max_val
        abs_setup.absinfo.fuzz = 0
        abs_setup.absinfo.flat = 0
        abs_setup.absinfo.resolution = resolution
        fcntl.ioctl(self.fd, UI_ABS_SETUP, abs_setup)

    def _create_device(self) -> None:
        """Configures and registers the uinput virtual tablet device."""
        uinput_path = "/dev/uinput"
        if not os.path.exists(uinput_path):
            raise FileNotFoundError("/dev/uinput does not exist. Ensure uinput kernel module is loaded.")

        self.fd = os.open(uinput_path, os.O_WRONLY | os.O_NONBLOCK)

        # 1. Enable Event Types
        for ev in (EV_SYN, EV_KEY, EV_ABS):
            fcntl.ioctl(self.fd, UI_SET_EVBIT, ev)

        # 2. Enable Digitizer Keys
        for key in (BTN_TOOL_PEN, BTN_TOUCH, BTN_STYLUS, BTN_STYLUS2):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, key)

        # 3. Enable Digitizer Axes
        for axis in (ABS_X, ABS_Y, ABS_PRESSURE):
            fcntl.ioctl(self.fd, UI_SET_ABSBIT, axis)

        # 4. Set Direct Input Property (Absolute Mapping)
        fcntl.ioctl(self.fd, UI_SET_PROPBIT, INPUT_PROP_DIRECT)

        # 5. Configure Axis Ranges & Resolutions
        self._setup_abs(ABS_X, self.max_x, self.resolution_x)
        self._setup_abs(ABS_Y, self.max_y, self.resolution_y)
        self._setup_abs(ABS_PRESSURE, self.max_pressure, 0)

        # 6. Device Identity Setup
        dev_setup = uinput_setup()
        dev_setup.id.bustype = BUS_USB
        dev_setup.id.vendor = self.vendor_id
        dev_setup.id.product = self.product_id
        dev_setup.id.version = 0x0001
        dev_setup.name = self.device_name.encode("utf-8")[:79]
        dev_setup.ff_effects_max = 0

        fcntl.ioctl(self.fd, UI_DEV_SETUP, dev_setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

        # Short pause to allow udev and compositors to initialize device node
        time.sleep(0.15)

    def _emit(self, ev_type: int, code: int, value: int) -> None:
        ev = input_event()
        ev.time.tv_sec = 0
        ev.time.tv_usec = 0
        ev.type = ev_type
        ev.code = code
        ev.value = value
        os.write(self.fd, bytes(ev))

    def _sync(self) -> None:
        self._emit(EV_SYN, SYN_REPORT, 0)

    def pen_down(self, x: int, y: int, pressure: int) -> None:
        """Emits pen proximity entry, contact touch-down, and coordinate update."""
        if not self._pen_in_proximity:
            self._emit(EV_KEY, BTN_TOOL_PEN, 1)
            self._pen_in_proximity = True

        if not self._pen_touching:
            self._emit(EV_KEY, BTN_TOUCH, 1)
            self._pen_touching = True

        self._emit(EV_ABS, ABS_X, max(0, min(self.max_x, x)))
        self._emit(EV_ABS, ABS_Y, max(0, min(self.max_y, y)))
        self._emit(EV_ABS, ABS_PRESSURE, max(0, min(self.max_pressure, pressure)))
        self._sync()

    def pen_move(self, x: int, y: int, pressure: int) -> None:
        """Emits continuous stroke motion coordinates and pressure."""
        self._emit(EV_ABS, ABS_X, max(0, min(self.max_x, x)))
        self._emit(EV_ABS, ABS_Y, max(0, min(self.max_y, y)))
        self._emit(EV_ABS, ABS_PRESSURE, max(0, min(self.max_pressure, pressure)))
        self._sync()

    def pen_up(self) -> None:
        """Emits contact lift and pen out-of-proximity."""
        if self._pen_touching:
            self._emit(EV_ABS, ABS_PRESSURE, 0)
            self._emit(EV_KEY, BTN_TOUCH, 0)
            self._pen_touching = False

        if self._pen_in_proximity:
            self._emit(EV_KEY, BTN_TOOL_PEN, 0)
            self._pen_in_proximity = False

        self._sync()

    def set_stylus_button(self, pressed: bool) -> None:
        """Toggles the stylus barrel button (e.g. for palette popup or eraser)."""
        # Guard: Only emit stylus buttons when pen is actively in proximity/touching
        if not self._pen_in_proximity:
            return

        if self._stylus_active != pressed:
            self._emit(EV_KEY, BTN_STYLUS, 1 if pressed else 0)
            self._sync()
            self._stylus_active = pressed

    def close(self) -> None:
        """Releases the virtual device cleanly."""
        if self.fd is not None:
            try:
                self.pen_up()
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
