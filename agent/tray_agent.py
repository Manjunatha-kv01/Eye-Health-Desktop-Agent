"""System tray icon (pystray) with Open Dashboard / Pause / Quit."""
from __future__ import annotations

import threading
from pathlib import Path

from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("tray_agent")


class TrayAgent:
    def __init__(self, on_open_dashboard, on_pause, on_resume, on_quit) -> None:
        self._open_dashboard = on_open_dashboard
        self._pause   = on_pause
        self._resume  = on_resume
        self._quit    = on_quit
        self._paused  = False
        self._icon    = None

    def run(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError as e:
            log.error("pystray/Pillow not installed: %s", e)
            return

        cfg = get_config()
        icon_path = Path(cfg.ui["tray_icon"])
        image = Image.open(icon_path) if icon_path.exists() else self._default_icon()

        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", self._cb_open),
            pystray.MenuItem("Pause / Resume", self._cb_toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._cb_quit),
        )
        self._icon = pystray.Icon("eye_health_agent", image, "Eye Health Agent", menu)
        log.info("Tray icon started.")
        self._icon.run()

    def update_icon(self, status: str) -> None:
        if not self._icon:
            return
        paths = {
            "ok":       "assets/icons/tray_ok.png",
            "warning":  "assets/icons/tray_warning.png",
            "critical": "assets/icons/tray_critical.png",
        }
        p = Path(paths.get(status, "assets/icons/tray_icon.png"))
        try:
            from PIL import Image
            if p.exists():
                self._icon.icon = Image.open(p)
        except Exception:
            pass

    def _cb_open(self, *_):
        threading.Thread(target=self._open_dashboard, daemon=True).start()

    def _cb_toggle_pause(self, *_):
        if self._paused:
            self._resume()
            self._paused = False
        else:
            self._pause()
            self._paused = True

    def _cb_quit(self, *_):
        self._quit()
        if self._icon:
            self._icon.stop()

    @staticmethod
    def _default_icon():
        from PIL import Image, ImageDraw
        img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(34, 197, 94, 255))
        draw.ellipse([18, 22, 46, 42], fill=(255, 255, 255, 255))
        draw.ellipse([27, 27, 37, 37], fill=(0, 100, 200, 255))
        return img
