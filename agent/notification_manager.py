"""Cross-platform desktop notifications via plyer."""
from __future__ import annotations

from pathlib import Path

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("notifications")

_APP  = "Eye Health Agent"
_TIMEOUT = 8

_TITLES = {
    "blink":    "👁  Blink Reminder",
    "distance": "📏  Screen Distance Warning",
    "posture":  "🧍  Posture Alert",
    "break":    "⏱  Time for a Break",
    "ambient":  "💡  Ambient Light Advisory",
    "score":    "📊  Daily Eye Score",
}
_ICONS = {
    "blink":    "assets/icons/blink.png",
    "distance": "assets/icons/distance.png",
    "posture":  "assets/icons/posture.png",
    "break":    "assets/icons/break.png",
    "ambient":  "assets/icons/ambient.png",
    "score":    "assets/icons/score.png",
    "default":  "assets/icons/tray_icon.png",
}


class NotificationManager:
    def __init__(self) -> None:
        self._enabled = get_config().notifications.get("enabled", True)

    def send(self, category: str, message: str) -> None:
        if not self._enabled:
            return
        title = _TITLES.get(category, _APP)
        icon  = _ICONS.get(category, _ICONS["default"])
        log.info("[%s] %s", category.upper(), message)
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name=_APP,
                app_icon=icon if Path(icon).exists() else None,
                timeout=_TIMEOUT,
            )
        except Exception as e:
            log.debug("plyer failed (%s) — console fallback", e)
            print(f"\n[{title}]\n{message}\n")
