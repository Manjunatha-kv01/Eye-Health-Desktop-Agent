"""
Eye Health Desktop Agent — Entry Point
"""
from __future__ import annotations

import signal
import sys
import threading

from utils.config import load_config
from utils.logger import setup_logger

log = setup_logger("main")


def main() -> None:
    log.info("Eye Health Desktop Agent starting…")

    from core.vision_engine import VisionEngine, VisionState
    from core.ambient_light import AmbientLightMonitor

    vision_state = VisionState()

    ambient = AmbientLightMonitor()
    ambient.start()

    vision = VisionEngine(vision_state)
    vision.start()

    from engine.eye_health_engine import EyeHealthEngine

    health = EyeHealthEngine(vision_state, ambient)
    health.start()

    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from dashboard.main_window import MainWindow
    from dashboard.break_overlay import BreakOverlay
    from agent.tray_agent import TrayAgent

    window: MainWindow | None = None

    def open_dashboard() -> None:
        nonlocal window
        if window is None or not window.isVisible():
            window = MainWindow(vision_state, health_engine=health)
            window.show()
        else:
            window.raise_()
            window.activateWindow()

    def pause_monitoring() -> None:
        vision.stop()
        health.stop()
        log.info("Monitoring paused.")

    def resume_monitoring() -> None:
        # Threads can't be restarted — spin up fresh ones
        nv = VisionEngine(vision_state)
        nv.start()
        nh = EyeHealthEngine(vision_state, ambient)
        nh.start()
        # Update window reference if dashboard is open
        nonlocal health
        health = nh
        log.info("Monitoring resumed.")

    def quit_app() -> None:
        vision.stop()
        health.stop()
        ambient.stop()
        app.quit()

    tray = TrayAgent(
        on_open_dashboard=open_dashboard,
        on_pause=pause_monitoring,
        on_resume=resume_monitoring,
        on_quit=quit_app,
    )
    threading.Thread(target=tray.run, daemon=True, name="TrayAgent").start()

    signal.signal(signal.SIGINT, lambda *_: quit_app())

    open_dashboard()

    log.info("Qt event loop running.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
