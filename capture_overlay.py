"""Freeze-frame full-desktop overlay with rubber-band selection."""

from __future__ import annotations

import mss
from PIL import Image

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QCursor, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget, QApplication


def grab_full_desktop() -> tuple[Image.Image, QRect]:
    """Snapshot the entire virtual desktop with mss. Returns (PIL image, virtual rect in logical px)."""
    with mss.mss() as sct:
        mon = sct.monitors[0]  # combined virtual desktop
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    app = QApplication.instance()
    union = QRect()
    for screen in app.screens():
        union = union.united(screen.geometry())

    return img, union


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    w, h = img.size
    raw = img.tobytes("raw", "RGBA")
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class CaptureOverlay(QWidget):
    """Full-desktop translucent overlay; emits crop_ready(PIL.Image, QRect) on release."""

    crop_ready = Signal(object, object)
    cancelled = Signal()

    def __init__(self, snapshot: Image.Image, virtual_rect: QRect) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(virtual_rect)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        self._snapshot = snapshot
        self._virtual_rect = virtual_rect

        # Scale frozen snapshot to logical widget size for painting.
        # Using FastTransformation avoids slowness on large desktops.
        self._bg_pixmap = pil_to_qpixmap(snapshot).scaled(
            virtual_rect.width(), virtual_rect.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._selecting = False

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)

        # 1. Frozen screenshot everywhere
        painter.drawPixmap(0, 0, self._bg_pixmap)

        # 2. Light-blue overlay everywhere
        painter.fillRect(self.rect(), QColor(100, 180, 255, 70))

        if self._selecting and self._origin and self._current:
            sel = self._selection_rect()
            if sel.width() > 0 and sel.height() > 0:
                # 3. Re-draw clear screenshot inside selection (overpaints tinted layer)
                painter.drawPixmap(sel, self._bg_pixmap, sel)

                # 4. Selection border
                pen = QPen(QColor("#5cb8ff"), 2)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)

                # 5. Dimension label
                self._draw_dimension_label(painter, sel)

        painter.end()

    def _selection_rect(self) -> QRect:
        return QRect(self._origin, self._current).normalized()

    def _draw_dimension_label(self, painter: QPainter, sel: QRect) -> None:
        label = f"{sel.width()} × {sel.height()}"
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 12
        th = fm.height() + 6

        lx = sel.right() - tw
        ly = sel.bottom() + 4
        if ly + th > self.height():
            ly = sel.top() - th - 4
        lx = max(0, min(lx, self.width() - tw))
        ly = max(0, ly)

        painter.fillRect(lx, ly, tw, th, QColor(30, 30, 34, 210))
        painter.setPen(QColor("#f2f2f5"))
        painter.drawText(lx + 6, ly + th - 6, label)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._selecting:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            self._current = event.position().toPoint()
            sel = self._selection_rect()
            self.hide()
            if sel.width() > 4 and sel.height() > 4:
                crop, screen_rect = self._make_crop(sel)
                self.crop_ready.emit(crop, screen_rect)
            else:
                self.cancelled.emit()
            self.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._selecting = False
            self.hide()
            self.cancelled.emit()
            self.deleteLater()

    # ------------------------------------------------------------------
    def _make_crop(self, sel_local: QRect) -> tuple[Image.Image, QRect]:
        """Map widget-local logical selection to a physical-pixel crop of the snapshot.

        Uses a simple ratio (snapshot_physical / virtual_logical) so it works
        correctly regardless of per-monitor DPR or mixed-DPI setups.
        """
        snap_w, snap_h = self._snapshot.size          # physical pixels
        virt_w = self._virtual_rect.width()            # logical pixels
        virt_h = self._virtual_rect.height()

        scale_x = snap_w / virt_w if virt_w else 1.0
        scale_y = snap_h / virt_h if virt_h else 1.0

        px = int(sel_local.x() * scale_x)
        py = int(sel_local.y() * scale_y)
        pw = max(1, int(sel_local.width() * scale_x))
        ph = max(1, int(sel_local.height() * scale_y))

        # Clamp to snapshot bounds
        px = max(0, min(px, snap_w - 1))
        py = max(0, min(py, snap_h - 1))
        pw = min(pw, snap_w - px)
        ph = min(ph, snap_h - py)

        crop = self._snapshot.crop((px, py, px + pw, py + ph))

        # Screen rect in global logical coords (for Hub placement)
        screen_rect = QRect(
            sel_local.x() + self._virtual_rect.x(),
            sel_local.y() + self._virtual_rect.y(),
            sel_local.width(),
            sel_local.height(),
        )
        return crop, screen_rect


def start_capture(on_crop, on_cancel=None) -> CaptureOverlay:
    """Grab desktop and show overlay. Must be called on the Qt main thread."""
    snapshot, virtual_rect = grab_full_desktop()
    overlay = CaptureOverlay(snapshot, virtual_rect)
    overlay.crop_ready.connect(on_crop)
    if on_cancel:
        overlay.cancelled.connect(on_cancel)
    # Use show() — showFullScreen() would override setGeometry() on multi-monitor setups
    overlay.show()
    overlay.raise_()
    overlay.activateWindow()
    return overlay
