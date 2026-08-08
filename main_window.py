"""Snippy main desktop window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame,
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
        self.setFixedSize(620, 420)

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

        # Top accent bar
        top_bar = QWidget()
        top_bar.setFixedHeight(6)
        top_bar.setStyleSheet(f"background: {config.ACCENT};")
        layout.addWidget(top_bar)

        layout.addWidget(self._build_command_bar())

        # Main content area
        content = QWidget()
        content.setStyleSheet(f"background: {config.BG};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(56, 62, 56, 30)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

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

        # Footer
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

    def _build_command_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        bar.setStyleSheet(f"""
            QWidget {{
                background: {config.SURFACE};
                border-bottom: 1px solid {config.BORDER};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        self._new_btn = self._make_command_btn("+  New", wide=True)
        self._snip_btn = self._make_command_btn("Snip")
        self._ruler_btn = self._make_command_btn("Ruler")
        self._color_btn = self._make_command_btn("Color")

        self._new_btn.setToolTip("Start a new snip")
        self._snip_btn.setToolTip("Capture a screen region")
        self._ruler_btn.setToolTip("Measure pixels with the ruler")
        self._color_btn.setToolTip("Pick a pixel color")

        self._new_btn.clicked.connect(lambda: self._start_capture("snip"))
        self._snip_btn.clicked.connect(lambda: self._start_capture("snip"))
        self._ruler_btn.clicked.connect(lambda: self._start_capture("ruler"))
        self._color_btn.clicked.connect(lambda: self._start_capture("color"))

        layout.addWidget(self._new_btn)
        layout.addSpacing(4)
        layout.addWidget(self._snip_btn)
        layout.addWidget(self._ruler_btn)
        layout.addWidget(self._color_btn)
        layout.addStretch()

        return bar

    def _make_command_btn(self, label: str, wide: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedSize(94 if wide else 76, 38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #FAFAFA;
                color: {config.TEXT};
                border: 1px solid {config.BORDER};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                padding: 0px 10px;
            }}
            QPushButton:hover {{
                background: #F1F1F1;
                border-color: {config.ACCENT};
            }}
            QPushButton:pressed {{
                background: #E8E8E8;
            }}
        """)
        return btn

    # ------------------------------------------------------------------
    def _on_capture_clicked(self) -> None:
        self._start_capture("snip")

    def _start_capture(self, mode: str) -> None:
        self.hide()
        # Small delay so the window is fully gone before the capture overlay appears
        QTimer.singleShot(150, lambda: self._capture_fn(mode))

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
