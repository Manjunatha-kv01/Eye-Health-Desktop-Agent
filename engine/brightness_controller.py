"""
Brightness Controller

Combines pupil-dilation hints (from PupillometryEngine) with ambient
light readings to automatically adjust screen brightness via
screen_brightness_control.

Algorithm
---------
1. Read PupilData.brightness_hint  →  INCREASE | DECREASE | HOLD
2. Weight the adjustment by how far the smoothed ratio deviates from
   the calibrated baseline — large deviation = larger step.
3. Apply a hard clamp [brightness_min, brightness_max].
4. Throttle: only apply once per `adjust_interval_seconds` to prevent
   flicker and give the user time to adapt.
5. Log every change.  Expose history for the dashboard sparkline.
"""
from __future__ import annotations

import collections
import time

import screen_brightness_control as sbc

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("brightness_ctrl")

_HISTORY_LEN = 120   # keep last 120 brightness readings (~16 min at 8s intervals)


class BrightnessController:
    """
    Stateful controller.  Call `update(pupil_data, ambient_lux)` from the
    engine loop.  It self-throttles; calling it every second is fine.
    """

    def __init__(self) -> None:
        cfg = get_config()
        p = cfg.pupillometry
        self._min      = int(p["brightness_min"])
        self._max      = int(p["brightness_max"])
        self._step     = int(p["brightness_step"])
        self._interval = float(p["adjust_interval_seconds"])
        self._dil_high = float(p["dilation_high"])
        self._dil_low  = float(p["dilation_low"])
        self._enabled  = bool(p.get("enabled", True))

        self._last_apply: float = 0.0
        self._current_brightness: int = self._safe_get_brightness()

        # Rolling history for the dashboard sparkline  (brightness %, timestamp)
        self.history: collections.deque[tuple[float, int]] = collections.deque(
            maxlen=_HISTORY_LEN
        )
        self.history.append((time.time(), self._current_brightness))

        self.last_action:    str = "HOLD"   # last hint applied
        self.last_reason:    str = ""
        self.auto_mode:      bool = True    # can be toggled from UI

        log.info(
            "BrightnessController ready — current=%d%%  range=[%d-%d]%%",
            self._current_brightness, self._min, self._max,
        )

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def update(self, pupil_data, ambient_lux: float) -> None:
        """
        Called every second from EyeHealthEngine.
        pupil_data : PupilData from PupillometryEngine
        ambient_lux: float from AmbientLightMonitor
        """
        if not self._enabled or not self.auto_mode:
            return
        if not pupil_data.is_calibrated:
            return   # wait for baseline

        now = time.time()
        if now - self._last_apply < self._interval:
            return   # throttle

        hint   = pupil_data.brightness_hint
        ratio  = pupil_data.smoothed_ratio
        base   = pupil_data.baseline_ratio
        delta  = abs(ratio - base)

        # Scale step by deviation magnitude (0–3× base step)
        scale     = min(3.0, delta / max(0.001, (self._dil_high - self._dil_low) / 2))
        adj_step  = max(1, round(self._step * scale))

        current = self._safe_get_brightness()
        new_val = current

        if hint == "INCREASE":
            new_val = min(self._max, current + adj_step)
            reason  = (
                f"pupil dilated (ratio={ratio:.4f} > threshold={self._dil_high:.3f})"
            )
        elif hint == "DECREASE":
            new_val = max(self._min, current - adj_step)
            reason  = (
                f"pupil constricted (ratio={ratio:.4f} < threshold={self._dil_low:.3f})"
            )
        else:
            # HOLD — but still do ambient-light override if extreme
            new_val, reason = self._ambient_override(current, ambient_lux)

        if new_val != current:
            self._apply(new_val)
            self.last_action = hint
            self.last_reason = reason
            log.info(
                "Brightness %d%% → %d%%  |  %s  (step=%d)",
                current, new_val, reason, adj_step,
            )

        self._last_apply = now

    def set_manual(self, brightness: int) -> None:
        """User manually sets brightness from dashboard slider."""
        val = max(self._min, min(self._max, brightness))
        self._apply(val)
        self.auto_mode = False
        log.info("Manual brightness set to %d%% — auto mode OFF", val)

    def enable_auto(self) -> None:
        self.auto_mode = True
        log.info("Auto brightness mode enabled.")

    def get_current(self) -> int:
        return self._current_brightness

    def get_history(self) -> list[tuple[float, int]]:
        """Returns list of (timestamp, brightness_pct)."""
        return list(self.history)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply(self, value: int) -> None:
        try:
            sbc.set_brightness(value, display=0)
            self._current_brightness = value
            self.history.append((time.time(), value))
        except Exception as e:
            log.warning("Failed to set brightness to %d%%: %s", value, e)

    def _safe_get_brightness(self) -> int:
        try:
            b = sbc.get_brightness(display=0)
            val = b[0] if isinstance(b, list) else b
            return int(val)
        except Exception:
            return self._current_brightness if hasattr(self, "_current_brightness") else 70

    def _ambient_override(self, current: int, lux: float) -> tuple[int, str]:
        """
        Fallback: use ambient lux when pupil hint is HOLD but environment
        is extreme (very dark or very bright room).
        """
        cfg = get_config()
        dim_thr    = cfg.ambient["dim_threshold"]
        bright_thr = cfg.ambient["bright_threshold"]

        if lux < dim_thr and current < 60:
            # Dark room + screen already dim → nudge up slightly
            return min(self._max, current + 2), f"ambient override dim ({lux:.0f} lux)"
        if lux > bright_thr and current > 80:
            # Very bright room + screen already bright → cap it
            return max(self._min, current - 2), f"ambient override bright ({lux:.0f} lux)"
        return current, "HOLD"
