"""Core background daemon loop, event processing, coordinate mapping, and IPC management."""

import os
import sys
import time
import select
import signal
import json
import logging
from typing import Optional, Dict, Any, Tuple

from .utils import (
    EV_SYN,
    EV_KEY,
    EV_ABS,
    SYN_REPORT,
    ABS_X,
    ABS_Y,
    ABS_MT_SLOT,
    ABS_MT_TRACKING_ID,
    ABS_MT_POSITION_X,
    ABS_MT_POSITION_Y,
    BTN_LEFT,
    BTN_TOUCH,
    BTN_TOOL_FINGER,
    INPUT_EVENT_SIZE,
    input_event,
    grab_device,
)
from .device import TouchpadInfo, get_touchpad, detect_display_resolution
from .filter import CoordinateSmoother, PseudoPressureCalculator
from .uinput_tablet import UInputTablet
from .config import TabletConfig
from .notifier import Notifier
from .ipc import IPCServer, write_daemon_pid, cleanup_ipc

logger = logging.getLogger("touchpad-tablet")


class TabletDaemon:
    """Orchestrates event capture, coordinate translation, filtering, and tablet synthesis."""

    def __init__(self, config: Optional[TabletConfig] = None):
        self.config = config or TabletConfig.load()
        self.touchpad_info: TouchpadInfo = get_touchpad(self.config.device)
        self.notifier = Notifier(enabled=self.config.notifications)

        # Detect Display Resolution
        if self.config.screen_width and self.config.screen_height:
            self.screen_width = self.config.screen_width
            self.screen_height = self.config.screen_height
        else:
            self.screen_width, self.screen_height = detect_display_resolution()

        logger.info(
            f"Using Touchpad: {self.touchpad_info.name} ({self.touchpad_info.path}) "
            f"[{self.touchpad_info.axis_x.maximum}x{self.touchpad_info.axis_y.maximum}]"
        )
        logger.info(f"Target Display: {self.screen_width}x{self.screen_height}")

        # Compute Aspect Ratio Geometry
        self._compute_geometry()

        # Coordinate Filtering & Dynamics
        self.smoother = CoordinateSmoother(
            smoothing=self.config.smoothing,
            use_one_euro=self.config.use_one_euro,
        )
        self.pressure_calc = PseudoPressureCalculator(
            min_pressure=self.config.pressure_min,
            max_pressure=self.config.pressure_max,
            curve_type=self.config.pressure_curve,
        )

        # State Variables
        self.touchpad_fd: Optional[int] = None
        self.uinput_tablet: Optional[UInputTablet] = None
        self.ipc_server: Optional[IPCServer] = None
        self.is_tablet_mode = False
        self.running = False

        # Multi-touch Tracking
        self.current_slot = 0
        self.primary_slot = 0
        self.slot_active: Dict[int, bool] = {}
        self.raw_x = 0
        self.raw_y = 0
        self.touch_down = False
        self.click_pressed = False

    def _compute_geometry(self) -> None:
        """Calculates scaling factors and letterboxing/pillarboxing offsets."""
        pad_w = float(self.touchpad_info.axis_x.range)
        pad_h = float(self.touchpad_info.axis_y.range)
        pad_aspect = pad_w / pad_h if pad_h > 0 else 1.0
        screen_aspect = float(self.screen_width) / float(self.screen_height) if self.screen_height > 0 else 1.0

        if self.config.aspect_ratio == "stretch":
            self.active_x_min = 0.0
            self.active_x_max = pad_w
            self.active_y_min = 0.0
            self.active_y_max = pad_h
        else:
            # "fit": Preserve screen aspect ratio on the physical pad surface
            if pad_aspect > screen_aspect:
                # Touchpad is wider than screen -> horizontal pillarboxing (margins on left/right)
                usable_w = pad_h * screen_aspect
                offset_x = (pad_w - usable_w) / 2.0
                self.active_x_min = offset_x
                self.active_x_max = pad_w - offset_x
                self.active_y_min = 0.0
                self.active_y_max = pad_h
            else:
                # Touchpad is taller than screen -> vertical letterboxing (margins on top/bottom)
                usable_h = pad_w / screen_aspect
                offset_y = (pad_h - usable_h) / 2.0
                self.active_x_min = 0.0
                self.active_x_max = pad_w
                self.active_y_min = offset_y
                self.active_y_max = pad_h - offset_y

        self.active_w = max(1.0, self.active_x_max - self.active_x_min)
        self.active_h = max(1.0, self.active_y_max - self.active_y_min)
        logger.info(
            f"Mapping Geometry ({self.config.aspect_ratio}): "
            f"X=[{self.active_x_min:.1f}, {self.active_x_max:.1f}], "
            f"Y=[{self.active_y_min:.1f}, {self.active_y_max:.1f}]"
        )

    def _map_coordinates(self, raw_x: float, raw_y: float) -> Tuple[int, int]:
        """Translates raw sensor coordinates into target tablet coordinate bounds."""
        norm_x = (raw_x - self.active_x_min) / self.active_w
        norm_y = (raw_y - self.active_y_min) / self.active_h

        # Clamp normalized coordinates to [0.0, 1.0]
        clamped_x = max(0.0, min(1.0, norm_x))
        clamped_y = max(0.0, min(1.0, norm_y))

        out_x = int(clamped_x * self.touchpad_info.axis_x.maximum)
        out_y = int(clamped_y * self.touchpad_info.axis_y.maximum)
        return out_x, out_y

    def enable_tablet_mode(self) -> None:
        """Enables 1:1 digitizer mode and grabs exclusive control of touchpad."""
        if self.is_tablet_mode:
            return
        logger.info("Enabling Tablet Mode (grabbing device)...")
        try:
            grab_device(self.touchpad_fd, grab=True)
            self.is_tablet_mode = True
            self.notifier.notify_mode_change(True)
        except OSError as e:
            logger.error(f"Failed to grab touchpad device: {e}")

    def disable_tablet_mode(self) -> None:
        """Releases exclusive control of touchpad, restoring normal cursor."""
        if not self.is_tablet_mode:
            return
        logger.info("Disabling Tablet Mode (releasing grab)...")
        try:
            if self.touch_down and self.uinput_tablet:
                self.uinput_tablet.pen_up()
                self.touch_down = False
            self.smoother.reset()
            self.pressure_calc.reset()
            grab_device(self.touchpad_fd, grab=False)
            self.is_tablet_mode = False
            self.notifier.notify_mode_change(False)
        except OSError as e:
            logger.error(f"Failed to release touchpad grab: {e}")

    def toggle_mode(self) -> bool:
        """Toggles between Tablet Mode and Mouse Mode."""
        if self.is_tablet_mode:
            self.disable_tablet_mode()
        else:
            self.enable_tablet_mode()
        return self.is_tablet_mode

    def _handle_ipc_command(self, cmd: str) -> str:
        """Processes IPC client requests."""
        cmd = cmd.strip().upper()
        if cmd == "STATUS":
            return json.dumps({
                "running": True,
                "mode": "tablet" if self.is_tablet_mode else "mouse",
                "device": self.touchpad_info.path,
                "device_name": self.touchpad_info.name,
                "screen_width": self.screen_width,
                "screen_height": self.screen_height,
                "aspect_ratio": self.config.aspect_ratio,
                "smoothing": self.config.smoothing,
            })
        elif cmd == "TOGGLE":
            mode = "tablet" if self.toggle_mode() else "mouse"
            return f"OK: {mode}"
        elif cmd == "ENABLE":
            self.enable_tablet_mode()
            return "OK: tablet"
        elif cmd == "DISABLE":
            self.disable_tablet_mode()
            return "OK: mouse"
        elif cmd == "STOP":
            self.running = False
            return "OK: stopping"
        else:
            return f"ERROR: Unknown command '{cmd}'"

    def _process_event_frame(self) -> None:
        """Invoked upon SYN_REPORT to flush buffered state to virtual tablet."""
        if not self.is_tablet_mode or not self.uinput_tablet:
            return

        if self.touch_down:
            mapped_x, mapped_y = self._map_coordinates(self.raw_x, self.raw_y)
            filtered_x, filtered_y = self.smoother.filter(mapped_x, mapped_y)
            pressure = self.pressure_calc.compute(filtered_x, filtered_y)

            # If clickpad is pressed and click_action is touch, boost pressure
            if self.click_pressed and self.config.click_action == "touch":
                pressure = self.config.pressure_max

            self.uinput_tablet.pen_move(int(filtered_x), int(filtered_y), pressure)
        else:
            self.uinput_tablet.pen_up()
            self.smoother.reset()
            self.pressure_calc.reset()

    def run(self) -> None:
        """Main daemon loop."""
        write_daemon_pid()
        self.touchpad_fd = os.open(self.touchpad_info.path, os.O_RDONLY | os.O_NONBLOCK)

        # Create the Virtual Tablet
        self.uinput_tablet = UInputTablet(
            max_x=self.touchpad_info.axis_x.maximum,
            max_y=self.touchpad_info.axis_y.maximum,
            max_pressure=self.config.pressure_max,
            resolution_x=self.touchpad_info.axis_x.resolution or 24,
            resolution_y=self.touchpad_info.axis_y.resolution or 24,
            device_name="Touchpad Virtual Graphics Tablet",
        )

        # Create IPC Server
        self.ipc_server = IPCServer(self._handle_ipc_command)

        # Register Signals
        def sig_handler(sig, frame):
            if sig == signal.SIGUSR1:
                self.toggle_mode()
            elif sig in (signal.SIGINT, signal.SIGTERM):
                self.running = False

        signal.signal(signal.SIGUSR1, sig_handler)
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        if self.config.start_mode == "tablet":
            self.enable_tablet_mode()
        else:
            logger.info("Started in Mouse Mode. Waiting for toggle command...")

        self.running = True
        poll_obj = select.poll()
        poll_obj.register(self.touchpad_fd, select.POLLIN)
        poll_obj.register(self.ipc_server.fileno, select.POLLIN)

        read_buf = bytearray(INPUT_EVENT_SIZE * 64)

        try:
            while self.running:
                events = poll_obj.poll(500)
                for fd, event_mask in events:
                    if fd == self.ipc_server.fileno:
                        self.ipc_server.handle_connection()
                    elif fd == self.touchpad_fd:
                        try:
                            bytes_read = os.readv(self.touchpad_fd, [read_buf]) if hasattr(os, "readv") else os.read(self.touchpad_fd, len(read_buf))
                        except BlockingIOError:
                            continue
                        except OSError as e:
                            logger.error(f"Error reading from touchpad: {e}")
                            break

                        num_events = bytes_read // INPUT_EVENT_SIZE
                        for i in range(num_events):
                            ev = input_event.from_buffer_copy(read_buf[i * INPUT_EVENT_SIZE : (i + 1) * INPUT_EVENT_SIZE])

                            if ev.type == EV_SYN and ev.code == SYN_REPORT:
                                self._process_event_frame()

                            elif ev.type == EV_ABS:
                                if ev.code == ABS_MT_SLOT:
                                    self.current_slot = ev.value
                                elif ev.code == ABS_MT_TRACKING_ID:
                                    if ev.value >= 0:
                                        self.slot_active[self.current_slot] = True
                                        if len(self.slot_active) == 1:
                                            self.primary_slot = self.current_slot
                                            self.touch_down = True
                                    else:
                                        self.slot_active.pop(self.current_slot, None)
                                        if self.current_slot == self.primary_slot or not self.slot_active:
                                            self.touch_down = False
                                            if self.slot_active:
                                                self.primary_slot = next(iter(self.slot_active))
                                                self.touch_down = True
                                elif ev.code in (ABS_MT_POSITION_X, ABS_X):
                                    if self.current_slot == self.primary_slot:
                                        self.raw_x = ev.value
                                elif ev.code in (ABS_MT_POSITION_Y, ABS_Y):
                                    if self.current_slot == self.primary_slot:
                                        self.raw_y = ev.value

                            elif ev.type == EV_KEY:
                                if ev.code in (BTN_TOUCH, BTN_TOOL_FINGER):
                                    # Fallback single touch handling if tracking id is omitted
                                    if not self.touchpad_info.has_multitouch:
                                        self.touch_down = (ev.value == 1)
                                elif ev.code == BTN_LEFT:
                                    self.click_pressed = (ev.value == 1)
                                    if self.config.click_action == "stylus" and self.uinput_tablet:
                                        self.uinput_tablet.set_stylus_button(self.click_pressed)

        finally:
            logger.info("Cleaning up daemon resources...")
            try:
                self.disable_tablet_mode()
            except Exception:
                pass
            if self.uinput_tablet:
                self.uinput_tablet.close()
            if self.touchpad_fd is not None:
                try:
                    os.close(self.touchpad_fd)
                except Exception:
                    pass
            if self.ipc_server:
                self.ipc_server.close()
            cleanup_ipc()
            logger.info("Daemon cleanly terminated.")
