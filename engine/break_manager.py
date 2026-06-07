"""Break Manager — 20-20-20 rule + long-break scheduling."""
from __future__ import annotations

import time
from typing import Callable

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("break_manager")


class BreakManager:
    def __init__(self) -> None:
        cfg = get_config()
        c = cfg.breaks
        self._short_s = c["work_interval_minutes"] * 60
        self._long_s  = c["long_break_interval_minutes"] * 60
        self._last_short = time.time()
        self._last_long  = time.time()
        self.breaks_taken  = 0
        self.breaks_missed = 0

    def tick(
        self,
        on_short_break: Callable[[], None],
        on_long_break: Callable[[], None],
    ) -> None:
        now = time.time()
        if now - self._last_short >= self._short_s:
            on_short_break()
            self.breaks_taken += 1
            self._last_short = now
        if now - self._last_long >= self._long_s:
            on_long_break()
            self.breaks_taken += 1
            self._last_long = now

    def compliance_ratio(self) -> float:
        total = self.breaks_taken + self.breaks_missed
        return 1.0 if total == 0 else self.breaks_taken / total

    def mark_missed(self) -> None:
        self.breaks_missed += 1

    def reset(self) -> None:
        self._last_short = time.time()
        self._last_long  = time.time()
        self.breaks_taken  = 0
        self.breaks_missed = 0
