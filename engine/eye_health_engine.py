"""
Eye Health Engine — central coordinator thread.
Reads vision state, fires alerts, manages breaks, calculates scores.
"""
from __future__ import annotations

import datetime
import threading
import time

from core.vision_engine import VisionState
from core.ambient_light import AmbientLightMonitor
from engine.break_manager import BreakManager
from engine.scoring import ScoringEngine
from engine.circadian import CircadianManager
from engine.brightness_controller import BrightnessController
from agent.notification_manager import NotificationManager
from utils.database import DatabaseManager
from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("eye_health_engine")


class EyeHealthEngine(threading.Thread):
    def __init__(self, vision_state: VisionState, ambient: AmbientLightMonitor) -> None:
        super().__init__(daemon=True, name="EyeHealthEngine")
        self.vision_state = vision_state
        self.ambient = ambient

        cfg = get_config()
        self._blink_cfg  = cfg.blink
        self._dist_cfg   = cfg.distance
        self._notif_cfg  = cfg.notifications

        self.notif   = NotificationManager()
        self.breaks  = BreakManager()
        self.scorer  = ScoringEngine()
        self.circadian = CircadianManager()
        self.db      = DatabaseManager.get_instance()
        self.brightness = BrightnessController()

        self._stop = threading.Event()
        self._session_id: int | None = None
        self._session_start: datetime.datetime | None = None
        self._distances: list[float] = []
        self._posture_alerts = 0
        self._last_notif: dict[str, float] = {}
        self._min_interval = self._notif_cfg.get("min_interval_seconds", 300)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        self._session_id = self.db.start_session()
        self._session_start = datetime.datetime.utcnow()
        tick = 0

        while not self._stop.is_set():
            state   = self.vision_state.snapshot()
            ambient = self.ambient.get_status()

            if state["face_detected"]:
                self._distances.append(state["distance_cm"])

            # Blink alert
            rate = state["blink_rate_per_min"]
            if state["face_detected"] and 0 < rate < self._blink_cfg["low_rate_threshold"]:
                self._notify("blink",
                    "👁  Low blink rate! Close your eyes gently for 2 seconds.")

            # Distance alert
            dist = state["distance_cm"]
            if state["face_detected"] and dist < self._dist_cfg["warning_cm"]:
                self._notify("distance",
                    f"📏  You're {dist:.0f} cm from the screen — move back to at least 40 cm.")

            # Posture alert
            if state.get("posture_alert"):
                self._posture_alerts += 1
                self.db.log_posture_event(state["head_offset_y"], "forward_head")
                self._notify("posture",
                    "🧍  Posture alert! Sit back and relax your shoulders.")

            # Ambient light
            rec = ambient["recommendation"]
            if rec == "DIM":
                self._notify("ambient",
                    "💡  Room is too dark — increase lighting or lower screen brightness.")
            elif rec == "BRIGHT":
                self._notify("ambient",
                    "☀️  Very bright room — consider raising screen brightness.")

            # Circadian
            self.circadian.apply_if_needed()

            # Pupillometry-driven brightness
            if state.get("pupil_calibrated"):
                self.brightness.update(
                    _PupilProxy(state), ambient["brightness_lux"]
                )
                # Notify user when auto-brightness acts
                action = self.brightness.last_action
                if action == "INCREASE":
                    self._notify("ambient",
                        f"🔆  Screen brightness raised automatically "
                        f"(pupils dilated — room may be too dim).")
                elif action == "DECREASE":
                    self._notify("ambient",
                        f"🔅  Screen brightness lowered automatically "
                        f"(pupils constricted — room is bright enough).")

            # Breaks
            self.breaks.tick(
                on_short_break=self._short_break,
                on_long_break=self._long_break,
            )

            # Score every 60 s
            if tick > 0 and tick % 60 == 0:
                self._save_score(state, ambient)

            tick += 1
            self._stop.wait(1.0)

        self._close_session()

    # ------------------------------------------------------------------

    def _short_break(self) -> None:
        self.notif.send("break",
            "⏱  20-20-20 Rule: Look 20 feet away for 20 seconds!")

    def _long_break(self) -> None:
        self.notif.send("break",
            "🛑  Time for a 5-minute break — stand up and stretch!")
        if get_config().breaks.get("mandatory_lock"):
            self._lock_screen()

    def _notify(self, cat: str, msg: str) -> None:
        now = time.time()
        if now - self._last_notif.get(cat, 0) >= self._min_interval:
            self.notif.send(cat, msg)
            self.db.log_notification(cat, msg)
            self._last_notif[cat] = now

    def _save_score(self, state: dict, ambient: dict) -> None:
        avg_dist = sum(self._distances) / len(self._distances) if self._distances else 60.0
        data = self.scorer.compute(
            blink_rate=state["blink_rate_per_min"],
            session_minutes=self._session_minutes(),
            distance_cm=avg_dist,
            break_compliance=self.breaks.compliance_ratio(),
            ambient_lux=ambient["brightness_lux"],
        )
        data["screen_time_minutes"] = self._session_minutes()
        data["date"] = datetime.datetime.utcnow()
        self.db.save_score(data)

    def _session_minutes(self) -> float:
        if not self._session_start:
            return 0.0
        return (datetime.datetime.utcnow() - self._session_start).total_seconds() / 60

    def _close_session(self) -> None:
        if self._session_id is None:
            return
        state = self.vision_state.snapshot()
        avg_dist = sum(self._distances) / len(self._distances) if self._distances else 60.0
        self.db.end_session(
            self._session_id,
            blink_count=state["blink_count"],
            avg_blink_rate=state["blink_rate_per_min"],
            avg_distance_cm=avg_dist,
            breaks_taken=self.breaks.breaks_taken,
            breaks_missed=self.breaks.breaks_missed,
            posture_alerts=self._posture_alerts,
        )

    @staticmethod
    def _lock_screen() -> None:
        import platform, subprocess, ctypes
        s = platform.system()
        try:
            if s == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"], check=False)
            elif s == "Linux":
                subprocess.run(["xdg-screensaver", "lock"], check=False)
            elif s == "Windows":
                ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            log.warning("Screen lock failed: %s", e)


class _PupilProxy:
    """
    Adapts a VisionState snapshot dict to the interface expected by
    BrightnessController.update() — avoids importing PupilData here.
    """
    __slots__ = (
        "is_calibrated", "smoothed_ratio", "baseline_ratio",
        "relative_dilation", "brightness_hint",
    )

    def __init__(self, state: dict) -> None:
        self.is_calibrated    = state.get("pupil_calibrated", False)
        self.smoothed_ratio   = state.get("pupil_smoothed", 0.0)
        self.baseline_ratio   = 0.0   # BrightnessController uses its own thresholds
        self.relative_dilation= state.get("relative_dilation", 0.0)
        self.brightness_hint  = state.get("brightness_hint", "HOLD")
