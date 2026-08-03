"""Snippy main desktop window."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QFont, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QApplication,
)

import config


class MainWindow(QMainWindow):
    """Primary Snippy desktop window."""

    def __init__(self, capture_fn) -> None:
        super().__init__()
        self._capture_fn = capture_fn
        self._setup_window()
        self._build_ui()

    def _setup_window(self) -> None:
        self.setWindowTitle("Snippy")
        logo = config.LOGO_PATH
        self.setWindowIcon(QIcon(logo))
        self.setFixedSize(400, 420)

        self.setStyleSheet(f"""
            QMainWindow, QWidget#central_widget {{
                background: {config.BG};
            }}
            QWidget {{
                font-family: 'Segoe UI', Arial, sans-serif;
            }}
        """)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central_widget")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top accent bar ─────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(6)
        top_bar.setStyleSheet(f"background: {config.ACCENT};")
        layout.addWidget(top_bar)

        # ── Main content area ──────────────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background: {config.BG};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 36, 40, 36)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Logo image
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(config.LOGO_PATH)
        if not pix.isNull():
            scaled = pix.scaled(
                200, 110,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(scaled)
        else:
            logo_lbl.setText("SNIPPY")
            logo_lbl.setStyleSheet(
                f"font-size: 28px; font-weight: 700; color: {config.ACCENT}; letter-spacing: 6px;"
            )
        content_layout.addWidget(logo_lbl)

        content_layout.addSpacing(28)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background: {config.BORDER}; margin: 0px 20px;")
        div.setFixedHeight(1)
        content_layout.addWidget(div)

        content_layout.addSpacing(28)

        # Instruction text
        instr = QLabel("Capture any region of your screen,\nthen copy, export, or search the content.")
        instr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instr.setWordWrap(True)
        instr.setStyleSheet(f"color: {config.MUTED}; font-size: 13px; line-height: 1.5;")
        content_layout.addWidget(instr)

        content_layout.addSpacing(28)

        # Capture button
        self._capture_btn = QPushButton("  Capture Screenshot")
        self._capture_btn.setFixedHeight(48)
        self._capture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._capture_btn.setStyleSheet(f"""
            QPushButton {{
                background: {config.ACCENT};
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{
                background: {config.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background: #000000;
            }}
            QPushButton:disabled {{
                background: {config.BORDER};
                color: {config.MUTED};
            }}
        """)
        self._capture_btn.clicked.connect(self._on_capture_clicked)
        content_layout.addWidget(self._capture_btn)

        content_layout.addSpacing(14)

        # Hotkey hint
        hint = QLabel(f"or press  {config.HOTKEY_DISPLAY}")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {config.MUTED}; font-size: 12px;")
        content_layout.addWidget(hint)

        content_layout.addStretch()

        # ── Footer ─────────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(46)
        footer.setStyleSheet(f"background: {config.SURFACE}; border-top: 1px solid {config.BORDER};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet(f"color: {config.MUTED}; font-size: 11px; background: transparent;")
        footer_layout.addWidget(self._status_lbl)
        footer_layout.addStretch()

        tray_note = QLabel("Closing hides to tray")
        tray_note.setStyleSheet(f"color: {config.BORDER}; font-size: 10px; background: transparent;")
        footer_layout.addWidget(tray_note)

        layout.addWidget(content)
        layout.addWidget(footer)

    # ------------------------------------------------------------------
    def _on_capture_clicked(self) -> None:
        self.hide()
        # Small delay so the window is fully gone before the capture overlay appears
        QTimer.singleShot(150, self._capture_fn)

    def set_status(self, msg: str, ok: bool = True) -> None:
        color = config.SUCCESS if ok else config.ERROR
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600; background: transparent;"
        )

    def show_after_capture(self) -> None:
        """Re-show the window after a capture session (if it was hidden)."""
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        # Minimise to tray instead of quitting
        event.ignore()
        self.hide()
