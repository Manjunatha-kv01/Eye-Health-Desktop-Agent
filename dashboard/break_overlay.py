"""Floating 20-20-20 break countdown overlay."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class BreakOverlay(QWidget):
    def __init__(self, duration_seconds: int = 20) -> None:
        super().__init__()
        self._duration  = duration_seconds
        self._remaining = duration_seconds
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "background-color: rgba(15,23,42,210); border-radius:16px;"
        )
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("👁️")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFont(QFont("Arial", 44))
        layout.addWidget(icon)

        title = QLabel("20 · 20 · 20 Eye Break")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#f1f5f9; font-size:20px; font-weight:700;")
        layout.addWidget(title)

        sub = QLabel("Look at something 20 feet (6 m) away")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color:#94a3b8; font-size:13px;")
        layout.addWidget(sub)

        self._cd = QLabel(str(self._remaining))
        self._cd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cd.setStyleSheet("color:#22c55e; font-size:46px; font-weight:900;")
        layout.addWidget(self._cd)

        btn = QPushButton("Skip")
        btn.setStyleSheet(
            "QPushButton{color:#64748b;background:transparent;"
            "border:1px solid #334155;border-radius:6px;padding:5px 18px;}"
            "QPushButton:hover{color:#f1f5f9;border-color:#64748b;}"
        )
        btn.clicked.connect(self.close)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        screen = QApplication.primaryScreen().geometry()
        self.setFixedSize(340, 260)
        self.move(screen.width() - 360, screen.height() - 310)

    def show_break(self) -> None:
        self._remaining = self._duration
        self._cd.setText(str(self._remaining))
        self.show()
        self._timer.start(1000)

    def _tick(self) -> None:
        self._remaining -= 1
        self._cd.setText(str(max(0, self._remaining)))
        if self._remaining <= 0:
            self._timer.stop()
            self.close()
