"""Stroke smoothing filters (One-Euro Filter, EMA) and velocity pseudo-pressure calculator."""

import math
import time
from typing import Tuple, Optional


class LowPassFilter:
    """Simple 1st-order exponential smoothing filter."""

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.s: Optional[float] = None

    def filter(self, value: float, alpha: Optional[float] = None) -> float:
        if alpha is not None:
            self.alpha = alpha
        if self.s is None:
            self.s = value
        else:
            self.s = self.alpha * value + (1.0 - self.alpha) * self.s
        return self.s

    def reset(self) -> None:
        self.s = None


class OneEuroFilter:
    """
    1€ Filter: Adaptive low-pass filter for noisy human input signals.
    Reduces jitter when moving slowly while minimizing latency during rapid movement.
    Reference: Casiez, Roussel, Vogel (CHI 2012)
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_filt = LowPassFilter()
        self.dx_filt = LowPassFilter()
        self.last_time: Optional[float] = None

    def _alpha(self, rate: float, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        te = 1.0 / rate if rate > 0 else 0.0
        return 1.0 / (1.0 + tau / te) if (tau + te) > 0 else 1.0

    def filter(self, x: float, timestamp: Optional[float] = None) -> float:
        now = timestamp if timestamp is not None else time.monotonic()
        if self.last_time is None:
            self.last_time = now
            return self.x_filt.filter(x, 1.0)

        dt = now - self.last_time
        self.last_time = now
        rate = 1.0 / dt if dt > 0.0001 else 120.0

        # Estimate derivative (speed)
        prev_x = self.x_filt.s if self.x_filt.s is not None else x
        dx = (x - prev_x) * rate
        edx = self.dx_filt.filter(dx, self._alpha(rate, self.d_cutoff))

        # Adapt cutoff frequency based on speed
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self.x_filt.filter(x, self._alpha(rate, cutoff))

    def reset(self) -> None:
        self.x_filt.reset()
        self.dx_filt.reset()
        self.last_time = None


class CoordinateSmoother:
    """Manages 2D coordinate smoothing with One-Euro or simple EMA."""

    def __init__(self, smoothing: float = 0.35, use_one_euro: bool = True):
        self.smoothing = max(0.0, min(1.0, smoothing))
        self.use_one_euro = use_one_euro
        if self.use_one_euro:
            # Scale parameters based on smoothing factor
            min_cutoff = max(0.2, 2.0 * (1.0 - self.smoothing))
            beta = 0.005 + 0.02 * (1.0 - self.smoothing)
            self.fx = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
            self.fy = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        else:
            alpha = max(0.05, 1.0 - self.smoothing)
            self.fx = LowPassFilter(alpha)
            self.fy = LowPassFilter(alpha)

    def filter(self, x: float, y: float, timestamp: Optional[float] = None) -> Tuple[float, float]:
        if self.smoothing <= 0.001:
            return x, y
        return self.fx.filter(x, timestamp), self.fy.filter(y, timestamp)

    def reset(self) -> None:
        self.fx.reset()
        self.fy.reset()


class PseudoPressureCalculator:
    """
    Synthesizes realistic stylus pressure from contact velocity and dwell dynamics.
    - Slower strokes produce firmer, higher pressure.
    - Swift flick strokes taper down smoothly into lighter pressure.
    """

    def __init__(
        self,
        min_pressure: int = 800,
        max_pressure: int = 4096,
        curve_type: str = "velocity",
    ):
        self.min_p = min_pressure
        self.max_p = max_pressure
        self.curve_type = curve_type
        self.last_x: Optional[float] = None
        self.last_y: Optional[float] = None
        self.last_time: Optional[float] = None
        self.pressure_filter = LowPassFilter(alpha=0.35)

    def compute(self, x: float, y: float, timestamp: Optional[float] = None) -> int:
        now = timestamp if timestamp is not None else time.monotonic()

        if self.curve_type == "constant":
            return int((self.min_p + self.max_p) / 2)

        if self.last_x is None or self.last_time is None:
            self.last_x = x
            self.last_y = y
            self.last_time = now
            # Initial touch-down starts moderately firm
            initial = int(self.min_p + (self.max_p - self.min_p) * 0.6)
            self.pressure_filter.filter(initial)
            return initial

        dt = now - self.last_time
        dx = x - self.last_x
        dy = y - self.last_y
        dist = math.hypot(dx, dy)

        self.last_x = x
        self.last_y = y
        self.last_time = now

        if dt <= 0.0001:
            speed = 0.0
        else:
            speed = dist / dt  # units per second

        # Map speed: 0 units/sec -> max pressure; 3000+ units/sec -> min pressure
        # Normal hand motion spans roughly 100 to 2500 units/second
        speed_norm = max(0.0, min(1.0, speed / 2500.0))

        # Inverted exponential curve: fast movement = lower pressure
        factor = math.exp(-2.2 * speed_norm)
        target_p = self.min_p + (self.max_p - self.min_p) * factor

        filtered_p = self.pressure_filter.filter(target_p)
        return int(max(self.min_p, min(self.max_p, filtered_p)))

    def reset(self) -> None:
        self.last_x = None
        self.last_y = None
        self.last_time = None
        self.pressure_filter.reset()
