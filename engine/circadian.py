"""Circadian Protection — reduces blue light in the evening/night."""
from __future__ import annotations

import datetime

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("circadian")


class CircadianManager:
    def __init__(self) -> None:
        cfg = get_config()
        self._cfg = cfg.circadian
        self._last_hour = -1

    def apply_if_needed(self) -> None:
        hour = datetime.datetime.now().hour
        if hour == self._last_hour:
            return
        self._last_hour = hour

        night   = self._cfg["night_start_hour"]
        evening = self._cfg["evening_start_hour"]

        if hour >= night or hour < 6:
            pct, mode = self._cfg["blue_light_reduction_night"], "night"
        elif hour >= evening:
            pct, mode = self._cfg["blue_light_reduction_evening"], "evening"
        else:
            pct, mode = 0, "day"

        if pct > 0:
            self._apply(pct)
            log.info("Circadian %s — blue light -%d%%", mode, pct)

    @staticmethod
    def _apply(pct: int) -> None:
        import platform, subprocess
        system = platform.system()
        try:
            if system == "Darwin":
                strength = pct / 100.0
                subprocess.run(
                    ["osascript", "-e",
                     f'tell application "System Events" to do shell script '
                     f'"defaults write com.apple.CoreBrightness '
                     f'CBBlueLightReductionStrength -float {strength}"'],
                    check=False, capture_output=True,
                )
            elif system == "Linux":
                temp = max(1000, int(6500 - (pct / 100) * 3500))
                subprocess.Popen(
                    ["redshift", "-O", str(temp), "-P"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
        except Exception as e:
            log.debug("Warm filter failed: %s", e)
