"""Ambient Light Monitor — estimates room brightness periodically."""
from __future__ import annotations

import threading

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("ambient_light")


class AmbientLightMonitor(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="AmbientLight")
        cfg = get_config()
        self._cfg = cfg.ambient
        self._stop_event = threading.Event()
        self.brightness_lux: float = 200.0
        self.recommendation: str = "OK"
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            lux = self._measure_lux()
            with self._lock:
                self.brightness_lux = lux
                if lux < self._cfg["dim_threshold"]:
                    self.recommendation = "DIM"
                elif lux > self._cfg["bright_threshold"]:
                    self.recommendation = "BRIGHT"
                else:
                    self.recommendation = "OK"
            log.debug("Ambient light: %.0f lux → %s", lux, self.recommendation)
            self._stop_event.wait(self._cfg["check_interval_seconds"])

    def get_status(self) -> dict:
        with self._lock:
            return {
                "brightness_lux": self.brightness_lux,
                "recommendation": self.recommendation,
            }

    def _measure_lux(self) -> float:
        for method in (self._from_screen_brightness, self._from_webcam):
            try:
                return method()
            except Exception:
                pass
        return 200.0

    @staticmethod
    def _from_screen_brightness() -> float:
        import screen_brightness_control as sbc
        b = sbc.get_brightness(display=0)
        return float(b[0] if isinstance(b, list) else b) * 10.0

    @staticmethod
    def _from_webcam() -> float:
        import cv2, numpy as np
        cap = cv2.VideoCapture(0, cv2.CAP_ANY)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise RuntimeError("webcam unreadable")
        return (float(np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))) / 255.0) * 1000.0
