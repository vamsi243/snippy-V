"""Floating Action Hub — spawns beside the drawn selection with preview + 5 action buttons."""

from __future__ import annotations

import time

from PIL import Image
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter, QPen, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QFileDialog, QApplication,
)

import config
from ocr.base import ParseResult

HUB_WIDTH = 310


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    raw = rgba.tobytes("raw", "RGBA")
    # Pass bytesPerLine explicitly; call .copy() so Qt owns the pixel buffer
    # before `raw` can be garbage-collected.
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


_BUTTON_DEFS = [
    ("📋  Copy Image",       "copy_image",       "Copy the screen crop to clipboard"),
    ("📝  Copy Text",        "copy_text",        "Copy recognised text to clipboard"),
    ("📊  Export CSV",       "export_csv",       "Save tabular data as CSV"),
    ("📄  Export PDF",       "export_pdf",       "Save text + table as PDF"),
    ("🔍  Circle to Search", "circle_to_search", "Search selected text in Brave"),
]


class ActionHub(QWidget):
    """Floating hub: preview thumbnail + 5 action buttons."""

    def __init__(
        self,
        crop: Image.Image,
        result: ParseResult,
        selection_rect: QRect,
        parent=None,
    ) -> None:
        # Use Window (not Tool) so the hub reliably receives mouse/keyboard events
        # on Windows. FramelessWindowHint + WindowStaysOnTopHint give the floating
        # feel without the focus-stealing baggage of Tool windows.
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Window,
        )

        self._crop = crop
        self._result = result
        self._selection_rect = selection_rect
        self._build_ui()

        self._auto_close = QTimer(self)
        self._auto_close.setSingleShot(True)
        self._auto_close.timeout.connect(self.close)
        self._auto_close.start(30000)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(f"""
            QWidget {{
                background: {config.SURFACE};
                color: {config.TEXT};
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(36)
        header.setStyleSheet(f"background: {config.ACCENT}; border-radius: 0px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 8, 0)

        title = QLabel("Snippy")
        title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 600; background: transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,180);
                border: none;
                font-size: 13px;
                padding: 0px;
            }
            QPushButton:hover { color: #FFFFFF; }
        """)
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        root.addWidget(header)

        # ── Body ──────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {config.SURFACE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 8)
        body_layout.setSpacing(0)

        # Preview thumbnail
        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            f"border: 1px solid {config.BORDER}; border-radius: 6px;"
            f"background: {config.BG}; padding: 2px;"
        )
        self._update_preview()
        body_layout.addWidget(self._preview_lbl)

        body_layout.addSpacing(8)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {config.BORDER}; margin: 0px;")
        sep.setFixedHeight(1)
        body_layout.addWidget(sep)

        body_layout.addSpacing(4)

        # Action buttons — store direct references to avoid collection errors
        self._btn_copy_image = self._make_btn("📋  Copy Image", "Copy the screen crop to clipboard")
        self._btn_copy_text = self._make_btn("📝  Copy Text", "Copy recognised text to clipboard")
        self._btn_export_csv = self._make_btn("📊  Export CSV", "Save tabular data as CSV")
        self._btn_export_pdf = self._make_btn("📄  Export PDF", "Save text + table as PDF")
        self._btn_search = self._make_btn("🔍  Search Text", "Search selected text in browser")

        for btn in (
            self._btn_copy_image,
            self._btn_copy_text,
            self._btn_export_csv,
            self._btn_export_pdf,
            self._btn_search,
        ):
            body_layout.addWidget(btn)

        body_layout.addSpacing(4)

        # Status bar
        self._status = QLabel("Ready")
        self._status.setObjectName("status_label")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setMinimumHeight(22)
        self._status.setStyleSheet(f"color: {config.MUTED}; font-size: 11px; padding: 2px 6px; background: transparent;")
        body_layout.addWidget(self._status)

        root.addWidget(body)

        # Wire buttons
        self._btn_copy_image.clicked.connect(self._copy_image)
        self._btn_copy_text.clicked.connect(self._copy_text)
        self._btn_export_csv.clicked.connect(self._export_csv)
        self._btn_export_pdf.clicked.connect(self._export_pdf)
        self._btn_search.clicked.connect(self._circle_to_search)

        # Start in loading state — text buttons disabled until OCR delivers a result
        self.set_ocr_loading(True)

    def _make_btn(self, label: str, tooltip: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {config.TEXT};
                border: none;
                border-radius: 6px;
                padding: 9px 14px;
                font-size: 13px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {config.ACCENT};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background: {config.ACCENT_HOVER};
                color: #FFFFFF;
            }}
        """)
        return btn

    def _update_preview(self) -> None:
        pix = pil_to_qpixmap(self._crop)
        if pix.isNull():
            self._preview_lbl.setText("No preview")
            self._preview_lbl.setFixedHeight(60)
            return
        max_w = HUB_WIDTH - 22
        max_h = 160
        scaled = pix.scaled(
            max_w, max_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_lbl.setPixmap(scaled)
        self._preview_lbl.setFixedSize(max_w, max(scaled.height(), 40))

    # ------------------------------------------------------------------
    def _position_near(self) -> None:
        sel = self._selection_rect
        # adjustSize() ensures sizeHint() reflects the actual layout after show()
        self.adjustSize()
        hub_w = self.width()
        hub_h = self.height()

        app = QApplication.instance()
        screen = app.primaryScreen()
        for s in app.screens():
            if s.geometry().contains(sel.center()):
                screen = s
                break
        avail = screen.availableGeometry()

        x = sel.center().x() - hub_w // 2
        y = sel.bottom() + 12

        if y + hub_h > avail.bottom():
            y = sel.top() - hub_h - 12
        if y < avail.top():
            y = avail.top() + 4

        x = max(avail.left() + 4, min(x, avail.right() - hub_w - 4))
        self.move(x, y)

    # ------------------------------------------------------------------
    _LOADING_BTN_STYLE = f"""
        QPushButton {{
            background: transparent;
            color: {config.BORDER};
            border: none;
            border-radius: 6px;
            padding: 9px 14px;
            font-size: 13px;
            text-align: left;
        }}
    """
    _NORMAL_BTN_STYLE = f"""
        QPushButton {{
            background: transparent;
            color: {config.TEXT};
            border: none;
            border-radius: 6px;
            padding: 9px 14px;
            font-size: 13px;
            text-align: left;
        }}
        QPushButton:hover {{
            background: {config.ACCENT};
            color: #FFFFFF;
        }}
        QPushButton:pressed {{
            background: {config.ACCENT_HOVER};
            color: #FFFFFF;
        }}
    """

    def set_ocr_loading(self, loading: bool) -> None:
        """Disable/enable text-dependent buttons and run a live elapsed-time counter."""
        for btn in (self._btn_copy_text, self._btn_search):
            btn.setEnabled(not loading)
            btn.setStyleSheet(
                self._LOADING_BTN_STYLE if loading else self._NORMAL_BTN_STYLE
            )

        if loading:
            self._ocr_start = time.monotonic()
            self._ocr_tick_timer = QTimer(self)
            self._ocr_tick_timer.setInterval(1000)
            self._ocr_tick_timer.timeout.connect(self._ocr_tick)
            self._ocr_tick_timer.start()
            self._ocr_elapsed = 0
            self._refresh_ocr_status()
        else:
            if hasattr(self, "_ocr_tick_timer"):
                self._ocr_tick_timer.stop()
            self.ocr_elapsed_s = time.monotonic() - getattr(self, "_ocr_start", time.monotonic())

    def _ocr_tick(self) -> None:
        self._ocr_elapsed = int(time.monotonic() - self._ocr_start)
        self._refresh_ocr_status()

    def _refresh_ocr_status(self) -> None:
        elapsed = getattr(self, "_ocr_elapsed", 0)
        self._status.setText(f"Recognising text… {elapsed}s")
        self._status.setStyleSheet(
            f"color: {config.MUTED}; font-size: 11px; padding: 2px 6px; background: transparent;"
        )

    def _reset_timer(self) -> None:
        self._auto_close.start(30000)

    def _set_status(self, msg: str, ok: bool = True) -> None:
        color = config.SUCCESS if ok else config.ERROR
        self._status.setText(msg)
        self._status.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; padding: 2px 6px; background: transparent;"
        )
        self._reset_timer()

    # ------------------------------------------------------------------
    def _copy_image(self) -> None:
        QApplication.clipboard().setPixmap(pil_to_qpixmap(self._crop))
        self._set_status("✓ Image copied to clipboard")

    def _copy_text(self) -> None:
        text = self._result.raw_text
        if not text.strip():
            self._set_status("⏳ Text recognising — try again shortly", ok=False)
            return
        QApplication.clipboard().setText(text)
        self._set_status("✓ Text copied to clipboard")

    def _export_csv(self) -> None:
        if not self._result.table:
            self._set_status("✗ No table detected in this crop", ok=False)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "snippy_table.csv", "CSV Files (*.csv)"
        )
        if path:
            import parser_engine
            parser_engine.export_csv(self._result.table, path)
            self._set_status("✓ CSV saved")

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "snippy_export.pdf", "PDF Files (*.pdf)"
        )
        if path:
            import parser_engine
            parser_engine.export_pdf(self._result, path)
            self._set_status("✓ PDF saved")

    def _circle_to_search(self) -> None:
        text = self._result.raw_text.strip()
        if not text:
            self._set_status("⏳ Text recognising — try again shortly", ok=False)
            return
        import parser_engine
        parser_engine.search_brave(text)
        self._set_status("✓ Opening search…")
        QTimer.singleShot(1500, self.close)

    # ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def mousePressEvent(self, event) -> None:
        self._reset_timer()
        super().mousePressEvent(event)

    # Allow dragging the hub by its header
    def _start_drag(self, pos) -> None:
        self._drag_pos = pos

    def mouseMoveEvent(self, event) -> None:
        if hasattr(self, "_drag_pos") and self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)


def show_hub(
    crop: Image.Image,
    result: ParseResult,
    selection_rect: QRect,
) -> ActionHub:
    hub = ActionHub(crop, result, selection_rect)
    hub.setFixedWidth(HUB_WIDTH)
    hub.show()
    hub._position_near()
    hub.raise_()
    hub.activateWindow()
    return hub
