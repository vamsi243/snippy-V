"""Android-style 'Circle to Search' screen-edge glow overlay.

A click-through transparent overlay that blooms a colored glow on the
screen edges with a bright highlight sweeping around the perimeter.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, QTimer, QRectF, QPropertyAnimation, QEasingCurve, Property,
)
from PySide6.QtGui import (
    QColor, QPainter, QRadialGradient, QLinearGradient, QPainterPath,
)
from PySide6.QtWidgets import QWidget, QApplication


class ScreenGlowOverlay(QWidget):
    """Full-desktop edge-glow flourish for 'Circle to Search'.

    Usage::

        glow = ScreenGlowOverlay(accent="#7c5cff")
        glow.play(on_finished=lambda: search_brave(text))
    """

    def __init__(
        self,
        accent: str = "#7c5cff",
        thickness_ratio: float = 0.04,
        duration_ms: int = 1200,
        fire_at: float = 0.45,
        parent=None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._accent = QColor(accent)
        self._thickness_ratio = thickness_ratio
        self._duration_ms = duration_ms
        self._fire_at = fire_at  # fraction of duration at which callback fires
        self._on_finished = None

        self._progress: float = 0.0  # 0 to 1 drives the animation
        self._sweep: float = 0.0    # 0 to 1 position of highlight sweep

        # Cover all screens
        app = QApplication.instance()
        from PySide6.QtCore import QRect
        union = QRect()
        for screen in app.screens():
            union = union.united(screen.geometry())
        self.setGeometry(union)

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 fps
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0

    def play(self, on_finished=None) -> None:
        self._on_finished = on_finished
        self._elapsed = 0
        self._progress = 0.0
        self._sweep = 0.0
        self._fired = False
        self.show()
        self.raise_()
        self._timer.start()

    def _tick(self) -> None:
        self._elapsed += 16
        t = min(self._elapsed / self._duration_ms, 1.0)
        self._progress = t
        self._sweep = t

        if not self._fired and t >= self._fire_at:
            self._fired = True
            if self._on_finished:
                self._on_finished()

        self.update()

        if t >= 1.0:
            self._timer.stop()
            self.hide()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        t = self._progress  # 0 to 1

        # Fade envelope: bloom in, hold, then fade out.
        if t < 0.3:
            alpha = t / 0.3
        elif t < 0.7:
            alpha = 1.0
        else:
            alpha = 1.0 - (t - 0.7) / 0.3
        alpha = max(0.0, min(1.0, alpha))

        thickness = int(min(w, h) * self._thickness_ratio)

        accent = QColor(self._accent)
        accent.setAlphaF(alpha * 0.85)

        # Draw glow on each edge
        for edge in ("top", "bottom", "left", "right"):
            grad = QLinearGradient()
            if edge == "top":
                grad.setStart(0, 0); grad.setFinalStop(0, thickness)
                rect = QRectF(0, 0, w, thickness)
            elif edge == "bottom":
                grad.setStart(0, h); grad.setFinalStop(0, h - thickness)
                rect = QRectF(0, h - thickness, w, thickness)
            elif edge == "left":
                grad.setStart(0, 0); grad.setFinalStop(thickness, 0)
                rect = QRectF(0, 0, thickness, h)
            else:  # right
                grad.setStart(w, 0); grad.setFinalStop(w - thickness, 0)
                rect = QRectF(w - thickness, 0, thickness, h)

            grad.setColorAt(0, accent)
            grad.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 0))
            painter.fillRect(rect, grad)

        # Sweep highlight: a bright spot travelling around the perimeter
        perimeter = 2 * (w + h)
        pos = (self._sweep * perimeter) % perimeter

        # Convert perimeter position to (cx, cy)
        if pos < w:
            cx, cy = pos, 0
        elif pos < w + h:
            cx, cy = w, pos - w
        elif pos < 2 * w + h:
            cx, cy = w - (pos - w - h), h
        else:
            cx, cy = 0, h - (pos - 2 * w - h)

        spot_r = thickness * 3
        spot = QRadialGradient(cx, cy, spot_r)
        highlight = QColor(255, 255, 255, int(220 * alpha))
        spot.setColorAt(0, highlight)
        spot.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(spot)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - spot_r, cy - spot_r, spot_r * 2, spot_r * 2))

        painter.end()
