"""Eye Strain Scoring Engine — computes 0-100 score from 5 factors."""
from __future__ import annotations
import math
from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("scoring")


class ScoringEngine:
    _BLINK_IDEAL   = 15.0
    _BLINK_MIN     = 5.0
    _SESSION_IDEAL = 20.0
    _SESSION_MAX   = 90.0
    _DIST_IDEAL    = 60.0
    _DIST_MIN      = 40.0
    _LUX_IDEAL     = 300.0
    _LUX_MIN       = 50.0
    _LUX_MAX       = 500.0

    def compute(
        self,
        blink_rate: float,
        session_minutes: float,
        distance_cm: float,
        break_compliance: float,
        ambient_lux: float,
    ) -> dict:
        cfg = get_config()
        w = cfg.scoring["weights"]

        b  = self._blink_score(blink_rate)
        s  = self._session_score(session_minutes)
        d  = self._distance_score(distance_cm)
        br = round(break_compliance * 100, 1)
        a  = self._ambient_score(ambient_lux)

        overall = round(
            max(0.0, min(100.0,
                b * w["blink_rate"] +
                s * w["session_length"] +
                d * w["distance"] +
                br * w["break_compliance"] +
                a * w["ambient_light"]
            )), 1
        )
        risk = "Low" if overall >= 70 else "Medium" if overall >= 45 else "High"

        return {
            "overall_score":   overall,
            "blink_score":     b,
            "session_score":   s,
            "distance_score":  d,
            "break_score":     br,
            "ambient_score":   a,
            "strain_risk":     risk,
        }

    def _blink_score(self, r: float) -> float:
        if r >= self._BLINK_IDEAL: return 100.0
        if r <= self._BLINK_MIN:   return 0.0
        return round((r - self._BLINK_MIN) / (self._BLINK_IDEAL - self._BLINK_MIN) * 100, 1)

    def _session_score(self, m: float) -> float:
        if m <= self._SESSION_IDEAL: return 100.0
        if m >= self._SESSION_MAX:   return 0.0
        return round(100 - (m - self._SESSION_IDEAL) / (self._SESSION_MAX - self._SESSION_IDEAL) * 100, 1)

    def _distance_score(self, d: float) -> float:
        if d >= self._DIST_IDEAL: return 100.0
        if d <= self._DIST_MIN:   return 0.0
        return round((d - self._DIST_MIN) / (self._DIST_IDEAL - self._DIST_MIN) * 100, 1)

    def _ambient_score(self, lux: float) -> float:
        if self._LUX_MIN <= lux <= self._LUX_MAX:
            return round(100.0 * math.exp(-((lux - self._LUX_IDEAL) ** 2) / (2 * 150.0 ** 2)), 1)
        return 20.0
