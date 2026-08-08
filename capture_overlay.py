"""Freeze-frame full-desktop overlay with rubber-band selection, pixel ruler, and color picker."""

from __future__ import annotations

import itertools
import mss
from PIL import Image

from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QCursor, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget, QApplication


def _relative_rect(rect: QRect, origin: QRect) -> QRect:
    return QRect(
        rect.x() - origin.x(),
        rect.y() - origin.y(),
        rect.width(),
        rect.height(),
    )


def _normalised_center(rect: QRect, bounds_w: int, bounds_h: int) -> tuple[float, float]:
    if bounds_w <= 0 or bounds_h <= 0:
        return 0.0, 0.0
    center = rect.center()
    return center.x() / bounds_w, center.y() / bounds_h


def _monitor_relative_rect(mon: dict, mon0: dict) -> QRect:
    return QRect(
        int(mon["left"] - mon0["left"]),
        int(mon["top"] - mon0["top"]),
        int(mon["width"]),
        int(mon["height"]),
    )


def _screen_monitor_score(screen, union_rect: QRect, monitor: dict, mon0: dict) -> float:
    """Score a Qt screen against an MSS monitor using size and desktop position."""
    geom = screen.geometry()
    rel = _relative_rect(geom, union_rect)
    dpr = float(screen.devicePixelRatio() or 1.0)

    expected_w = max(1, int(round(geom.width() * dpr)))
    expected_h = max(1, int(round(geom.height() * dpr)))
    size_score = (
        abs(monitor["width"] - expected_w) / max(monitor["width"], expected_w, 1)
        + abs(monitor["height"] - expected_h) / max(monitor["height"], expected_h, 1)
    )

    qcx, qcy = _normalised_center(rel, union_rect.width(), union_rect.height())
    mrel = _monitor_relative_rect(monitor, mon0)
    mcx, mcy = _normalised_center(mrel, mon0["width"], mon0["height"])
    position_score = abs(qcx - mcx) + abs(qcy - mcy)

    return size_score * 0.7 + position_score * 0.3


def _assign_monitors(screens: list, monitors: list[dict], union_rect: QRect, mon0: dict) -> list[dict]:
    """Return one MSS monitor per Qt screen, preserving layout for 1/2/3+ screens."""
    if not monitors:
        return [mon0 for _ in screens]
    if len(screens) == 1:
        return [monitors[0]]

    screen_count = len(screens)
    monitor_count = len(monitors)
    best_assignment: tuple[dict, ...] | None = None
    best_score = float("inf")

    for perm in itertools.permutations(monitors, min(screen_count, monitor_count)):
        score = 0.0
        for screen, monitor in zip(screens, perm):
            score += _screen_monitor_score(screen, union_rect, monitor, mon0)
        if score < best_score:
            best_score = score
            best_assignment = perm

    assigned = list(best_assignment or ())
    while len(assigned) < screen_count:
        assigned.append(monitors[min(len(assigned), monitor_count - 1)])
    return assigned


def _build_screen_map(screens: list, union_rect: QRect, monitors: list[dict], mon0: dict) -> list[dict]:
    assigned_monitors = _assign_monitors(screens, monitors, union_rect, mon0)
    screen_map = []

    for screen, monitor in zip(screens, assigned_monitors):
        geom = screen.geometry()
        rel_rect = _relative_rect(geom, union_rect)
        phys_rect = _monitor_relative_rect(monitor, mon0)
        scale_x = phys_rect.width() / rel_rect.width() if rel_rect.width() else 1.0
        scale_y = phys_rect.height() / rel_rect.height() if rel_rect.height() else 1.0
        cover_rect = QRect(geom)

        screen_map.append({
            "screen": screen,
            "name": screen.name(),
            "log_rect": geom,
            "rel_log_rect": rel_rect,
            "mss_mon": monitor,
            "phys_rect": phys_rect,
            "phys_x": phys_rect.x(),
            "phys_y": phys_rect.y(),
            "cover_rect": cover_rect,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "dpr": float(screen.devicePixelRatio() or 1.0),
        })

    return screen_map


def _screen_sort_key(screen) -> tuple[int, int, str]:
    geom = screen.geometry()
    return (geom.x(), geom.y(), screen.name())


def grab_full_desktop() -> tuple[Image.Image, QRect, dict]:
    """Snapshot the entire virtual desktop with mss and compute precise per-screen mappings."""
    app = QApplication.instance()
    screens = sorted(app.screens(), key=_screen_sort_key) if app is not None else []

    try:
        with mss.mss() as sct:
            mon0 = sct.monitors[0]  # combined physical virtual desktop
            raw = sct.grab(mon0)
            snapshot = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            all_monitors = sct.monitors[1:]
    except Exception:
        try:
            from PIL import ImageGrab
            snapshot = ImageGrab.grab(all_screens=True).convert("RGB")
            mon0 = {"left": 0, "top": 0, "width": snapshot.width, "height": snapshot.height}
            all_monitors = [mon0]
        except Exception:
            snapshot = Image.new("RGB", (1920, 1080), (40, 40, 40))
            mon0 = {"left": 0, "top": 0, "width": 1920, "height": 1080}
            all_monitors = [mon0]



    if screens:
        union_rect = QRect(screens[0].geometry())
        for screen in screens[1:]:
            union_rect = union_rect.united(screen.geometry())
        screen_map = _build_screen_map(screens, union_rect, all_monitors, mon0)
    else:
        union_rect = QRect(int(mon0["left"]), int(mon0["top"]), int(mon0["width"]), int(mon0["height"]))
        screen_map = [{
            "screen": None,
            "name": f"Monitor_{i+1}",
            "log_rect": QRect(int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])),
            "rel_log_rect": _relative_rect(QRect(int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])), union_rect),
            "mss_mon": m,
            "phys_rect": _monitor_relative_rect(m, mon0),
            "phys_x": int(m["left"] - mon0["left"]),
            "phys_y": int(m["top"] - mon0["top"]),
            "cover_rect": QRect(int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])),
            "scale_x": 1.0,
            "scale_y": 1.0,
            "dpr": 1.0,
        } for i, m in enumerate(all_monitors)]

    mapping_info = {
        "union_rect": union_rect,
        "mon0": mon0,
        "screen_map": screen_map,
    }

    return snapshot, union_rect, mapping_info


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    w, h = img.size
    raw = img.tobytes("raw", "RGBA")
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def build_screen_bg(snapshot: Image.Image, window_rect: QRect, screen_info: dict) -> QPixmap:
    """Build the frozen desktop background for one monitor overlay."""
    bg_image = QImage(window_rect.width(), window_rect.height(), QImage.Format.Format_RGBA8888)
    bg_image.fill(QColor(0, 0, 0, 255))

    painter = QPainter(bg_image)
    phys_rect = screen_info["phys_rect"]
    left = max(0, phys_rect.left())
    top = max(0, phys_rect.top())
    right = min(snapshot.width, phys_rect.left() + phys_rect.width())
    bottom = min(snapshot.height, phys_rect.top() + phys_rect.height())
    if right > left and bottom > top:
        mon_crop = snapshot.crop((left, top, right, bottom))
        mon_pixmap = pil_to_qpixmap(mon_crop).scaled(
            window_rect.width(),
            window_rect.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        painter.drawPixmap(0, 0, mon_pixmap)
    painter.end()

    return QPixmap.fromImage(bg_image)


class CaptureOverlay(QWidget):
    """Full-desktop translucent overlay supporting Rubberband Snip, Ruler, and Color Picker."""

    crop_ready = Signal(object, object)
    cancelled = Signal()

    MODE_SNIP = 0
    MODE_RULER = 1
    MODE_COLOR_PICKER = 2
    MODE_NAMES = {
        "snip": MODE_SNIP,
        "ruler": MODE_RULER,
        "color": MODE_COLOR_PICKER,
    }

    def __init__(
        self,
        snapshot: Image.Image,
        virtual_rect: QRect,
        mapping_info: dict,
        initial_mode: str | int = MODE_SNIP,
        window_rect: QRect | None = None,
        window_info: dict | None = None,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self._window_info = window_info
        self._window_rect = QRect(window_rect or virtual_rect)
        self.setGeometry(self._window_rect)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._snapshot = snapshot
        self._virtual_rect = virtual_rect
        self._mapping_info = mapping_info
        self._screen_map = mapping_info["screen_map"]
        if self._window_info is None and self._screen_map:
            self._window_info = self._screen_map[0]

        # Build accurate multi-monitor composite background
        self._bg_pixmap = build_screen_bg(snapshot, self._window_rect, self._window_info)

        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._cursor_pos: QPoint = QPoint(0, 0)
        self._selecting = False
        self._mode = self._coerce_mode(initial_mode)

        if self._mode == self.MODE_COLOR_PICKER:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def _coerce_mode(self, mode: str | int) -> int:
        if isinstance(mode, int):
            return mode if mode in self.MODE_NAMES.values() else self.MODE_SNIP
        return self.MODE_NAMES.get(mode, self.MODE_SNIP)

    def show_on_screen(self) -> None:
        if self._window_info is not None:
            self.winId()
            handle = self.windowHandle()
            if handle is not None:
                handle.setScreen(self._window_info["screen"])
        self.setGeometry(self._window_rect)
        self.showFullScreen()
        self.setGeometry(self._window_rect)
        self.raise_()

    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)

        # 1. Frozen screenshot everywhere
        painter.drawPixmap(0, 0, self._bg_pixmap)

        # 2. Translucent tint overlay
        painter.fillRect(self.rect(), QColor(30, 35, 45, 85))

        # 3. Top toolbar guide
        self._draw_toolbar(painter)

        is_shift_ruler = (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ) or (self._mode == self.MODE_RULER)

        # Mode: Color Picker
        if self._mode == self.MODE_COLOR_PICKER:
            self._draw_color_picker(painter)
        elif self._selecting and self._origin and self._current:
            sel = self._selection_rect()
            if sel.width() > 0 and sel.height() > 0:
                # Re-draw clear screenshot inside selection
                painter.drawPixmap(sel, self._bg_pixmap, sel)

                if is_shift_ruler:
                    # Ruler styling
                    pen = QPen(QColor("#00e5ff"), 2, Qt.PenStyle.DashLine)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(sel)
                    self._draw_ruler_details(painter, sel)
                else:
                    # Standard snip selection
                    pen = QPen(QColor("#5cb8ff"), 2)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(sel)
                    self._draw_dimension_label(painter, sel)

        painter.end()

    def _selection_rect(self) -> QRect:
        return QRect(self._origin, self._current).normalized()

    def _local_to_virtual_point(self, pt_local: QPoint) -> QPoint:
        if self._window_info is not None:
            rel_rect = self._window_info["rel_log_rect"]
            cover_rect = self._window_info["cover_rect"]
            scale_x = cover_rect.width() / rel_rect.width() if rel_rect.width() else 1.0
            scale_y = cover_rect.height() / rel_rect.height() if rel_rect.height() else 1.0
            return QPoint(
                rel_rect.x() + int(round(pt_local.x() / scale_x)),
                rel_rect.y() + int(round(pt_local.y() / scale_y)),
            )

        return QPoint(
            pt_local.x() + self._window_rect.x() - self._virtual_rect.x(),
            pt_local.y() + self._window_rect.y() - self._virtual_rect.y(),
        )

    def _local_to_virtual_rect(self, rect_local: QRect) -> QRect:
        top_left = self._local_to_virtual_point(rect_local.topLeft())
        bottom_right = self._local_to_virtual_point(rect_local.bottomRight())
        return QRect(top_left, bottom_right).normalized()

    def _draw_toolbar(self, painter: QPainter) -> None:
        bar_w = 452
        bar_h = 32
        x = (self.width() - bar_w) // 2
        y = 12

        painter.fillRect(x, y, bar_w, bar_h, QColor(20, 22, 28, 220))
        pen = QPen(QColor(255, 255, 255, 40), 1)
        painter.setPen(pen)
        painter.drawRect(x, y, bar_w, bar_h)

        font = QFont("Segoe UI", 10)
        painter.setFont(font)

        items = [
            ("[Drag] Snip", self._mode == self.MODE_SNIP),
            ("[Shift+Drag] Ruler", self._mode == self.MODE_RULER),
            ("[C] Color Picker", self._mode == self.MODE_COLOR_PICKER),
            ("[Esc] Cancel", False),
        ]

        curr_x = x + 12
        for text, active in items:
            if active:
                painter.setPen(QColor("#5cb8ff"))
            else:
                painter.setPen(QColor("#d0d0d5"))
            painter.drawText(curr_x, y + 21, text)
            curr_x += 108

    def _draw_dimension_label(self, painter: QPainter, sel: QRect, prefix: str = "") -> None:
        label = f"{prefix}{sel.width()} x {sel.height()} px"
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 14
        th = fm.height() + 6

        lx = sel.right() - tw
        ly = sel.bottom() + 4
        if ly + th > self.height():
            ly = sel.top() - th - 4
        lx = max(0, min(lx, self.width() - tw))
        ly = max(0, ly)

        painter.fillRect(lx, ly, tw, th, QColor(30, 30, 34, 220))
        painter.setPen(QColor("#f2f2f5"))
        painter.drawText(lx + 7, ly + th - 6, label)

    def _draw_ruler_details(self, painter: QPainter, sel: QRect) -> None:
        label = f"W: {sel.width()}px  |  H: {sel.height()}px"
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 16
        th = fm.height() + 8

        lx = sel.right() + 8
        ly = sel.bottom() + 8
        if lx + tw > self.width():
            lx = sel.left() - tw - 8
        if ly + th > self.height():
            ly = sel.top() - th - 8
        lx = max(0, min(lx, self.width() - tw))
        ly = max(0, min(ly, self.height() - th))

        painter.fillRect(lx, ly, tw, th, QColor(10, 25, 40, 230))
        pen = QPen(QColor("#00e5ff"), 1)
        painter.setPen(pen)
        painter.drawRect(lx, ly, tw, th)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(lx + 8, ly + th - 7, label)

        # Draw corner crosshairs
        ch_len = 8
        pen_ch = QPen(QColor("#00e5ff"), 1.5)
        painter.setPen(pen_ch)
        for pt in (sel.topLeft(), sel.topRight(), sel.bottomLeft(), sel.bottomRight()):
            painter.drawLine(pt.x() - ch_len, pt.y(), pt.x() + ch_len, pt.y())
            painter.drawLine(pt.x(), pt.y() - ch_len, pt.x(), pt.y() + ch_len)

    def _draw_color_picker(self, painter: QPainter) -> None:
        pos = self._cursor_pos
        px, py = self._logical_to_physical(pos)

        r, g, b = 0, 0, 0
        snap_w, snap_h = self._snapshot.size
        if 0 <= px < snap_w and 0 <= py < snap_h:
            r, g, b = self._snapshot.getpixel((px, py))

        hex_code = f"#{r:02X}{g:02X}{b:02X}"

        # Draw target reticle at cursor
        ret_size = 10
        pen_ret = QPen(QColor("#ffffff"), 1.5)
        painter.setPen(pen_ret)
        painter.drawLine(pos.x() - ret_size, pos.y(), pos.x() + ret_size, pos.y())
        painter.drawLine(pos.x(), pos.y() - ret_size, pos.x(), pos.y() + ret_size)

        # Draw floating tooltip near cursor
        tt_w = 140
        tt_h = 42
        tx = pos.x() + 16
        ty = pos.y() + 16
        if tx + tt_w > self.width():
            tx = pos.x() - tt_w - 16
        if ty + tt_h > self.height():
            ty = pos.y() - tt_h - 16

        painter.fillRect(tx, ty, tt_w, tt_h, QColor(20, 22, 28, 230))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawRect(tx, ty, tt_w, tt_h)

        # Color swatch box
        swatch_rect = QRect(tx + 8, ty + 9, 24, 24)
        painter.fillRect(swatch_rect, QColor(r, g, b))
        painter.setPen(QColor("#ffffff"))
        painter.drawRect(swatch_rect)

        # Text labels
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(tx + 40, ty + 20, hex_code)

        font_sub = QFont("Segoe UI", 8)
        painter.setFont(font_sub)
        painter.setPen(QColor("#a0a0a5"))
        painter.drawText(tx + 40, ty + 33, f"RGB: {r},{g},{b}")

    # ------------------------------------------------------------------
    def _logical_to_physical(self, pt_local: QPoint) -> tuple[int, int]:
        """Convert logical overlay coordinate to snapshot physical coordinate."""
        pt_virtual = self._local_to_virtual_point(pt_local)
        for info in self._screen_map:
            rel_rect = info["rel_log_rect"]
            if rel_rect.contains(pt_virtual):
                dx = pt_virtual.x() - rel_rect.x()
                dy = pt_virtual.y() - rel_rect.y()
                px = info["phys_x"] + int(round(dx * info["scale_x"]))
                py = info["phys_y"] + int(round(dy * info["scale_y"]))
                return self._clamp_physical_point(px, py)

        # Fallback ratio
        snap_w, snap_h = self._snapshot.size
        virt_w = self._virtual_rect.width()
        virt_h = self._virtual_rect.height()
        scale_x = snap_w / virt_w if virt_w else 1.0
        scale_y = snap_h / virt_h if virt_h else 1.0
        return self._clamp_physical_point(
            int(round(pt_virtual.x() * scale_x)),
            int(round(pt_virtual.y() * scale_y)),
        )

    def _clamp_physical_point(self, px: int, py: int) -> tuple[int, int]:
        snap_w, snap_h = self._snapshot.size
        return (
            max(0, min(px, snap_w - 1)),
            max(0, min(py, snap_h - 1)),
        )

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cursor_pos = event.position().toPoint()

            if self._mode == self.MODE_COLOR_PICKER:
                px, py = self._logical_to_physical(self._cursor_pos)
                r, g, b = 0, 0, 0
                snap_w, snap_h = self._snapshot.size
                if 0 <= px < snap_w and 0 <= py < snap_h:
                    r, g, b = self._snapshot.getpixel((px, py))
                hex_code = f"#{r:02X}{g:02X}{b:02X}"
                QApplication.clipboard().setText(hex_code)
                self.hide()
                self.cancelled.emit()
                self.deleteLater()
                return

            self._origin = self._cursor_pos
            self._current = self._origin
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event) -> None:
        self._cursor_pos = event.position().toPoint()
        if self._selecting:
            self._current = self._cursor_pos
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            self._current = event.position().toPoint()
            sel = self._selection_rect()

            is_shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)

            if is_shift or self._mode == self.MODE_RULER:
                # Ruler measurement complete; keep overlay active for further measurements.
                self.update()
                return

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
        elif event.key() == Qt.Key.Key_C:
            self._mode = (
                self.MODE_SNIP if self._mode == self.MODE_COLOR_PICKER else self.MODE_COLOR_PICKER
            )
            self.setCursor(QCursor(
                Qt.CursorShape.PointingHandCursor
                if self._mode == self.MODE_COLOR_PICKER
                else Qt.CursorShape.CrossCursor
            ))
            self.update()

    # ------------------------------------------------------------------
    def _make_crop(self, sel_local: QRect) -> tuple[Image.Image, QRect]:
        """Map local logical selection to physical snapshot crop screen-by-screen."""
        sel_virtual = self._local_to_virtual_rect(sel_local)
        final_crop = self._make_crop_from_snapshot(self._snapshot, sel_virtual)
        screen_rect = QRect(
            sel_virtual.x() + self._virtual_rect.x(),
            sel_virtual.y() + self._virtual_rect.y(),
            sel_virtual.width(),
            sel_virtual.height(),
        )
        return final_crop, screen_rect

    def _make_crop_from_snapshot(self, snapshot: Image.Image, sel_virtual: QRect) -> Image.Image:
        crops = []
        for info in self._screen_map:
            rel_rect = info["rel_log_rect"]
            inter = sel_virtual.intersected(rel_rect)
            if not inter.isEmpty() and inter.width() > 0 and inter.height() > 0:
                dx_log = inter.x() - rel_rect.x()
                dy_log = inter.y() - rel_rect.y()

                px = info["phys_x"] + int(round(dx_log * info["scale_x"]))
                py = info["phys_y"] + int(round(dy_log * info["scale_y"]))
                pw = max(1, int(round(inter.width() * info["scale_x"])))
                ph = max(1, int(round(inter.height() * info["scale_y"])))

                snap_w, snap_h = snapshot.size
                px = max(0, min(px, snap_w - 1))
                py = max(0, min(py, snap_h - 1))
                pw = min(pw, snap_w - px)
                ph = min(ph, snap_h - py)

                sub_crop = snapshot.crop((px, py, px + pw, py + ph))
                crops.append((px, py, sub_crop))

        if not crops:
            snap_w, snap_h = snapshot.size
            scale_x = snap_w / self._virtual_rect.width() if self._virtual_rect.width() else 1.0
            scale_y = snap_h / self._virtual_rect.height() if self._virtual_rect.height() else 1.0
            px = max(0, min(int(sel_virtual.x() * scale_x), snap_w - 1))
            py = max(0, min(int(sel_virtual.y() * scale_y), snap_h - 1))
            pw = min(max(1, int(sel_virtual.width() * scale_x)), snap_w - px)
            ph = min(max(1, int(sel_virtual.height() * scale_y)), snap_h - py)
            return snapshot.crop((px, py, px + pw, py + ph))
        elif len(crops) == 1:
            return crops[0][2]

        min_x = min(px for px, _, _ in crops)
        min_y = min(py for _, py, _ in crops)
        max_x = max(px + sub.width for px, _, sub in crops)
        max_y = max(py + sub.height for _, py, sub in crops)
        final_crop = Image.new("RGB", (max(1, max_x - min_x), max(1, max_y - min_y)))
        for px, py, sub in crops:
            final_crop.paste(sub, (px - min_x, py - min_y))
        return final_crop

class CaptureSession:
    """Owns one overlay window per monitor for mixed-DPI stability."""

    def __init__(self, snapshot: Image.Image, virtual_rect: QRect, mapping_info: dict, on_crop, on_cancel=None, initial_mode: str | int = "snip") -> None:
        self._on_crop = on_crop
        self._on_cancel = on_cancel
        self._finished = False
        self._overlays: list[CaptureOverlay] = []

        for info in mapping_info["screen_map"]:
            overlay = CaptureOverlay(
                snapshot,
                virtual_rect,
                mapping_info,
                initial_mode=initial_mode,
                window_rect=info["cover_rect"],
                window_info=info,
            )
            overlay.crop_ready.connect(self._handle_crop)
            overlay.cancelled.connect(self._handle_cancel)
            self._overlays.append(overlay)

    def show(self) -> None:
        for overlay in self._overlays:
            overlay.show_on_screen()

        if self._overlays:
            self._overlays[0].activateWindow()
            self._overlays[0].setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def close(self) -> None:
        for overlay in self._overlays:
            overlay.hide()
            overlay.deleteLater()
        self._overlays.clear()

    def _handle_crop(self, crop, selection_rect) -> None:
        if self._finished:
            return
        self._finished = True
        self.close()
        self._on_crop(crop, selection_rect)

    def _handle_cancel(self) -> None:
        if self._finished:
            return
        self._finished = True
        self.close()
        if self._on_cancel:
            self._on_cancel()


def start_capture(on_crop, on_cancel=None, initial_mode: str | int = "snip") -> CaptureSession:
    """Grab desktop and show overlay. Must be called on the Qt main thread."""
    snapshot, virtual_rect, mapping_info = grab_full_desktop()
    session = CaptureSession(
        snapshot,
        virtual_rect,
        mapping_info,
        on_crop=on_crop,
        on_cancel=on_cancel,
        initial_mode=initial_mode,
    )
    session.show()
    return session
