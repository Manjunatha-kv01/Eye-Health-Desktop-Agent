"""
Main Dashboard Window (PyQt6) — dark mode.
Shows live camera feed, real-time metrics, daily summary, weekly chart,
and the new Pupillometry / Auto-Brightness panel.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QProgressBar, QScrollArea, QSizePolicy,
    QSlider, QSplitter, QVBoxLayout, QWidget,
)

from core.vision_engine import VisionState
from utils.database import DatabaseManager, NotificationLog
from utils.config import get_config
from utils.logger import setup_logger

log = setup_logger("dashboard")


class MetricCard(QFrame):
    def __init__(self, title: str, unit: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "MetricCard{background:#1e293b;border-radius:12px;"
            "border:1px solid #334155;}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(88)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)

        self._title = QLabel(title)
        self._title.setStyleSheet("color:#94a3b8;font-size:10px;font-weight:600;")

        self._value = QLabel("—")
        self._value.setStyleSheet("color:#f1f5f9;font-size:24px;font-weight:700;")

        self._unit = QLabel(unit)
        self._unit.setStyleSheet("color:#64748b;font-size:10px;")

        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._unit)

    def set_value(self, value: str, color: str = "#f1f5f9") -> None:
        self._value.setText(value)
        self._value.setStyleSheet(
            f"color:{color};font-size:24px;font-weight:700;"
        )


class WeeklyChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(110)
        self._data: list[dict] = []

    def set_data(self, data: list[dict]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QPainter, QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._data:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return

        w, h, n = self.width(), self.height(), len(self._data)
        bar_w = max(8, (w - 20) // (n * 2))
        gap   = bar_w
        sx    = (w - n * (bar_w + gap)) // 2

        for i, d in enumerate(self._data):
            score = d.get("overall_score", 0)
            bh    = int(score / 100 * (h - 28))
            x     = sx + i * (bar_w + gap)
            y     = h - 18 - bh
            color = (
                QColor("#22c55e") if score >= 70
                else QColor("#f59e0b") if score >= 45
                else QColor("#ef4444")
            )
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_w, bh, 3, 3)
            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(x, h - 2, d.get("date", ""))


class BrightnessSparkline(QWidget):
    """Mini line-chart showing brightness history over the last N readings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(60)
        self._data: list[int] = []   # brightness % values

    def set_data(self, data: list[int]) -> None:
        self._data = data[-60:]      # last 60 points
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtGui import QPainter, QPen, QPainterPath

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if len(self._data) < 2:
            painter.setPen(QColor("#64748b"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Collecting data…")
            return

        w, h = self.width(), self.height()
        pad  = 6
        n    = len(self._data)
        step = (w - 2 * pad) / max(1, n - 1)

        path = QPainterPath()
        for i, val in enumerate(self._data):
            x = pad + i * step
            y = h - pad - (val / 100.0) * (h - 2 * pad)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(QColor("#22c55e"), 2)
        painter.setPen(pen)
        painter.drawPath(path)

        # Current value label
        cur = self._data[-1]
        painter.setPen(QColor("#f1f5f9"))
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        painter.drawText(w - 36, 14, f"{cur}%")


class MainWindow(QMainWindow):
    def __init__(self, vision_state: VisionState, health_engine=None) -> None:
        super().__init__()
        self.vs  = vision_state
        self.db  = DatabaseManager.get_instance()
        self._health_engine = health_engine   # may be None
        cfg = get_config()

        self.setWindowTitle("Eye Health Agent — Dashboard")
        self.setMinimumSize(1100, 720)
        self._apply_theme()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._right_panel())
        splitter.setSizes([480, 620])
        splitter.setStyleSheet("QSplitter::handle{background:#334155;width:2px;}")
        root.addWidget(splitter)

        self._timer = QTimer()
        self._timer.setInterval(cfg.ui["refresh_interval_ms"])
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    # ------------------------------------------------------------------

    def _left_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        cam_grp = QGroupBox("Live Feed")
        cam_grp.setStyleSheet(self._grp())
        cl = QVBoxLayout(cam_grp)
        self._cam_lbl = QLabel("Camera starting…")
        self._cam_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_lbl.setMinimumSize(400, 290)
        self._cam_lbl.setStyleSheet(
            "background:#0f172a;border-radius:8px;color:#64748b;"
        )
        cl.addWidget(self._cam_lbl)
        lay.addWidget(cam_grp)

        metrics_grp = QGroupBox("Live Metrics")
        metrics_grp.setStyleSheet(self._grp())
        mg = QGridLayout(metrics_grp)
        mg.setSpacing(8)
        self._c_blink   = MetricCard("BLINK RATE",       "blinks/min")
        self._c_dist    = MetricCard("SCREEN DISTANCE",  "cm")
        self._c_posture = MetricCard("POSTURE",           "")
        self._c_ear     = MetricCard("EAR",               "")
        mg.addWidget(self._c_blink,   0, 0)
        mg.addWidget(self._c_dist,    0, 1)
        mg.addWidget(self._c_posture, 1, 0)
        mg.addWidget(self._c_ear,     1, 1)
        lay.addWidget(metrics_grp)
        return w

    def _right_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        sum_grp = QGroupBox("Today's Summary")
        sum_grp.setStyleSheet(self._grp())
        sg = QGridLayout(sum_grp)
        sg.setSpacing(8)
        self._c_time   = MetricCard("SCREEN TIME",    "")
        self._c_blinks = MetricCard("BLINKS TODAY",   "")
        self._c_breaks = MetricCard("BREAKS TAKEN",   "")
        self._c_score  = MetricCard("EYE SCORE",      "/ 100")
        sg.addWidget(self._c_time,   0, 0)
        sg.addWidget(self._c_blinks, 0, 1)
        sg.addWidget(self._c_breaks, 1, 0)
        sg.addWidget(self._c_score,  1, 1)
        lay.addWidget(sum_grp)

        risk_grp = QGroupBox("Eye Strain Risk")
        risk_grp.setStyleSheet(self._grp())
        rl = QVBoxLayout(risk_grp)
        self._risk_lbl = QLabel("—")
        self._risk_lbl.setStyleSheet("color:#22c55e;font-size:18px;font-weight:700;")
        self._risk_bar = QProgressBar()
        self._risk_bar.setRange(0, 100)
        self._risk_bar.setTextVisible(False)
        self._risk_bar.setFixedHeight(10)
        self._risk_bar.setStyleSheet(
            "QProgressBar{background:#1e293b;border-radius:5px;}"
            "QProgressBar::chunk{background:#22c55e;border-radius:5px;}"
        )
        rl.addWidget(self._risk_lbl)
        rl.addWidget(self._risk_bar)
        lay.addWidget(risk_grp)

        # ---- Pupillometry + Auto-Brightness panel ----
        lay.addWidget(self._pupillometry_panel())

        chart_grp = QGroupBox("Weekly Eye Scores")
        chart_grp.setStyleSheet(self._grp())
        chl = QVBoxLayout(chart_grp)
        self._chart = WeeklyChart()
        chl.addWidget(self._chart)
        lay.addWidget(chart_grp)

        notif_grp = QGroupBox("Recent Alerts")
        notif_grp.setStyleSheet(self._grp())
        nl = QVBoxLayout(notif_grp)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(110)
        self._scroll.setStyleSheet("background:#0f172a;border:none;")
        self._notif_w = QWidget()
        self._notif_l = QVBoxLayout(self._notif_w)
        self._notif_l.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._notif_w)
        nl.addWidget(self._scroll)
        lay.addWidget(notif_grp)

        lay.addStretch()
        return w

    def _pupillometry_panel(self) -> QGroupBox:
        """Pupillometry & Auto-Brightness control panel."""
        grp = QGroupBox("👁  Pupillometry & Auto-Brightness")
        grp.setStyleSheet(self._grp())
        outer = QVBoxLayout(grp)
        outer.setSpacing(8)

        # ---- Top row: metric cards ----
        top = QHBoxLayout()
        self._c_pupil_ratio  = MetricCard("PUPIL RATIO",        "normalised")
        self._c_pupil_diam   = MetricCard("IRIS DIAMETER",      "px")
        self._c_gaze_zone    = MetricCard("GAZE ZONE",           "")
        self._c_brightness   = MetricCard("SCREEN BRIGHTNESS",  "%")
        for card in (self._c_pupil_ratio, self._c_pupil_diam,
                     self._c_gaze_zone, self._c_brightness):
            top.addWidget(card)
        outer.addLayout(top)

        # ---- Calibration status bar ----
        calib_row = QHBoxLayout()
        calib_lbl = QLabel("Calibration:")
        calib_lbl.setStyleSheet("color:#64748b;font-size:10px;")
        self._calib_bar = QProgressBar()
        self._calib_bar.setRange(0, 100)
        self._calib_bar.setValue(0)
        self._calib_bar.setFixedHeight(8)
        self._calib_bar.setTextVisible(False)
        self._calib_bar.setStyleSheet(
            "QProgressBar{background:#0f172a;border-radius:4px;}"
            "QProgressBar::chunk{background:#6366f1;border-radius:4px;}"
        )
        self._calib_status = QLabel("Collecting baseline…")
        self._calib_status.setStyleSheet("color:#6366f1;font-size:10px;")
        calib_row.addWidget(calib_lbl)
        calib_row.addWidget(self._calib_bar, stretch=1)
        calib_row.addWidget(self._calib_status)
        outer.addLayout(calib_row)

        # ---- Brightness hint indicator ----
        hint_row = QHBoxLayout()
        hint_lbl = QLabel("Brightness hint:")
        hint_lbl.setStyleSheet("color:#64748b;font-size:10px;")
        self._hint_badge = QLabel("HOLD")
        self._hint_badge.setStyleSheet(
            "background:#334155;color:#94a3b8;padding:2px 10px;"
            "border-radius:4px;font-size:11px;font-weight:700;"
        )
        hint_row.addWidget(hint_lbl)
        hint_row.addWidget(self._hint_badge)
        hint_row.addStretch()

        # Auto mode toggle
        self._auto_chk = QCheckBox("Auto-adjust brightness")
        self._auto_chk.setChecked(True)
        self._auto_chk.setStyleSheet("color:#94a3b8;font-size:11px;")
        self._auto_chk.toggled.connect(self._on_auto_toggle)
        hint_row.addWidget(self._auto_chk)
        outer.addLayout(hint_row)

        # ---- Manual brightness slider (shown when auto OFF) ----
        slider_row = QHBoxLayout()
        slider_lbl = QLabel("Manual:")
        slider_lbl.setStyleSheet("color:#64748b;font-size:10px;")
        self._brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self._brightness_slider.setRange(10, 100)
        self._brightness_slider.setValue(70)
        self._brightness_slider.setEnabled(False)
        self._brightness_slider.setStyleSheet(
            "QSlider::groove:horizontal{background:#334155;height:4px;"
            "border-radius:2px;}"
            "QSlider::handle:horizontal{background:#6366f1;width:14px;"
            "height:14px;border-radius:7px;margin:-5px 0;}"
            "QSlider::sub-page:horizontal{background:#6366f1;border-radius:2px;}"
        )
        self._brightness_slider.valueChanged.connect(self._on_slider_change)
        self._slider_val_lbl = QLabel("70%")
        self._slider_val_lbl.setStyleSheet("color:#94a3b8;font-size:10px;width:32px;")
        slider_row.addWidget(slider_lbl)
        slider_row.addWidget(self._brightness_slider, stretch=1)
        slider_row.addWidget(self._slider_val_lbl)
        outer.addLayout(slider_row)

        # ---- Sparkline ----
        sparkline_lbl = QLabel("Brightness history")
        sparkline_lbl.setStyleSheet("color:#64748b;font-size:10px;")
        outer.addWidget(sparkline_lbl)
        self._sparkline = BrightnessSparkline()
        outer.addWidget(self._sparkline)

        return grp

    # ------------------------------------------------------------------
    # Refresh cycle
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._update_live()
        self._update_summary()
        self._update_chart()
        self._update_notifs()
        self._update_camera()
        self._update_pupillometry()

    def _update_live(self) -> None:
        s = self.vs.snapshot()
        rate = s.get("blink_rate_per_min", 0)
        c = "#22c55e" if rate >= 12 else "#f59e0b" if rate >= 8 else "#ef4444"
        self._c_blink.set_value(f"{rate:.0f}", c)

        dist = s.get("distance_cm", 0)
        self._c_dist.set_value(f"{dist:.0f}", "#22c55e" if dist >= 40 else "#ef4444")

        ok = not s.get("posture_alert", False)
        self._c_posture.set_value("✓ Good" if ok else "⚠ Alert",
                                   "#22c55e" if ok else "#ef4444")
        self._c_ear.set_value(f"{s.get('ear', 0):.2f}")

    def _update_pupillometry(self) -> None:
        s = self.vs.snapshot()

        # Pupil ratio
        ratio = s.get("pupil_smoothed", 0.0)
        self._c_pupil_ratio.set_value(f"{ratio:.4f}")

        # Iris diameter
        diam = s.get("pupil_diameter_px", 0.0)
        self._c_pupil_diam.set_value(f"{diam:.1f}")

        # Gaze zone
        zone = s.get("gaze_zone", "—")
        zone_color = {
            "Top":    "#f59e0b",
            "Centre": "#22c55e",
            "Bottom": "#6366f1",
        }.get(zone, "#94a3b8")
        self._c_gaze_zone.set_value(zone, zone_color)

        # Brightness controller
        if self._health_engine and hasattr(self._health_engine, "brightness"):
            bc = self._health_engine.brightness
            cur = bc.get_current()
            self._c_brightness.set_value(f"{cur}", "#f1f5f9")
            # Update slider
            self._brightness_slider.blockSignals(True)
            self._brightness_slider.setValue(cur)
            self._brightness_slider.blockSignals(False)
            self._slider_val_lbl.setText(f"{cur}%")
            # Sparkline
            history = [v for _, v in bc.get_history()]
            self._sparkline.set_data(history)

        # Calibration progress
        calibrated = s.get("pupil_calibrated", False)
        if calibrated:
            self._calib_bar.setValue(100)
            self._calib_status.setText("✓ Calibrated")
            self._calib_status.setStyleSheet("color:#22c55e;font-size:10px;")
        else:
            # Estimate progress: EMA starts immediately; use ratio > 0 as proxy
            pct = min(99, int(ratio * 1000)) if ratio > 0 else 0
            self._calib_bar.setValue(pct)
            self._calib_status.setText("Collecting baseline…")

        # Hint badge
        hint = s.get("brightness_hint", "HOLD")
        badge_styles = {
            "INCREASE": "background:#166534;color:#4ade80;",
            "DECREASE": "background:#1e3a5f;color:#60a5fa;",
            "HOLD":     "background:#334155;color:#94a3b8;",
        }
        self._hint_badge.setText(hint)
        self._hint_badge.setStyleSheet(
            badge_styles.get(hint, badge_styles["HOLD"])
            + "padding:2px 10px;border-radius:4px;font-size:11px;font-weight:700;"
        )

    def _update_summary(self) -> None:
        try:
            d = self.db.get_today_summary()
            m = d.get("screen_time_minutes", 0)
            h, mn = divmod(int(m), 60)
            self._c_time.set_value(f"{h}h {mn}m")
            self._c_blinks.set_value(str(d.get("blink_count", 0)))
            self._c_breaks.set_value(str(d.get("breaks_taken", 0)))

            sc = d.get("overall_score", 0)
            sc_c = "#22c55e" if sc >= 70 else "#f59e0b" if sc >= 45 else "#ef4444"
            self._c_score.set_value(f"{sc:.0f}", sc_c)

            risk = d.get("strain_risk", "Unknown")
            rc = {"Low": "#22c55e", "Medium": "#f59e0b", "High": "#ef4444"}.get(risk, "#94a3b8")
            self._risk_lbl.setText(risk)
            self._risk_lbl.setStyleSheet(f"color:{rc};font-size:18px;font-weight:700;")
            self._risk_bar.setValue({"Low": 20, "Medium": 55, "High": 90}.get(risk, 0))
            self._risk_bar.setStyleSheet(
                "QProgressBar{background:#1e293b;border-radius:5px;}"
                f"QProgressBar::chunk{{background:{rc};border-radius:5px;}}"
            )
        except Exception as e:
            log.debug("Summary refresh: %s", e)

    def _update_chart(self) -> None:
        try:
            self._chart.set_data(self.db.get_weekly_scores())
        except Exception as e:
            log.debug("Chart refresh: %s", e)

    def _update_notifs(self) -> None:
        try:
            with self.db.get_session() as sess:
                rows = (
                    sess.query(NotificationLog)
                    .order_by(NotificationLog.sent_at.desc())
                    .limit(6)
                    .all()
                )
            for i in reversed(range(self._notif_l.count())):
                w = self._notif_l.itemAt(i).widget()
                if w:
                    w.deleteLater()
            for r in rows:
                ts = r.sent_at.strftime("%H:%M") if r.sent_at else ""
                lbl = QLabel(f"[{ts}] {r.message}")
                lbl.setWordWrap(True)
                lbl.setStyleSheet("color:#94a3b8;font-size:11px;padding:2px 4px;")
                self._notif_l.addWidget(lbl)
        except Exception as e:
            log.debug("Notif refresh: %s", e)

    def _update_camera(self) -> None:
        frame = self.vs.frame_rgb
        if frame is None:
            return
        try:
            h, w, ch = frame.shape
            qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_BGR888)
            pix  = QPixmap.fromImage(qimg).scaled(
                self._cam_lbl.width(), self._cam_lbl.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._cam_lbl.setPixmap(pix)
        except Exception as e:
            log.debug("Camera refresh: %s", e)

    # ------------------------------------------------------------------
    # Brightness controls
    # ------------------------------------------------------------------

    def _on_auto_toggle(self, checked: bool) -> None:
        self._brightness_slider.setEnabled(not checked)
        if self._health_engine and hasattr(self._health_engine, "brightness"):
            bc = self._health_engine.brightness
            if checked:
                bc.enable_auto()
            else:
                bc.auto_mode = False

    def _on_slider_change(self, value: int) -> None:
        self._slider_val_lbl.setText(f"{value}%")
        if not self._auto_chk.isChecked():
            if self._health_engine and hasattr(self._health_engine, "brightness"):
                self._health_engine.brightness.set_manual(value)

    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow,QWidget{background:#0f172a;color:#f1f5f9;
              font-family:'SF Pro Display','Segoe UI',Arial,sans-serif;}
            QScrollBar:vertical{background:#1e293b;width:6px;}
            QScrollBar::handle:vertical{background:#334155;border-radius:3px;}
            QCheckBox{color:#94a3b8;}
            QCheckBox::indicator{width:14px;height:14px;border-radius:3px;
              border:1px solid #334155;background:#1e293b;}
            QCheckBox::indicator:checked{background:#6366f1;border-color:#6366f1;}
            """
        )

    @staticmethod
    def _grp() -> str:
        return (
            "QGroupBox{background:#1e293b;border:1px solid #334155;"
            "border-radius:10px;padding:8px;margin-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;"
            "subcontrol-position:top left;padding:0 6px;"
            "background:transparent;color:#64748b;}"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        event.accept()
