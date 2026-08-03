"""Snippy entry point: main window, system tray, global hotkey, wiring."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

import config


# ---------------------------------------------------------------------------
# Thread-safe bridges: background threads → Qt main thread
# ---------------------------------------------------------------------------

class _Bridge(QObject):
    trigger = Signal()
    ocr_done = Signal(object)   # carries ParseResult (or None)


_bridge = _Bridge()


# ---------------------------------------------------------------------------
# Global hotkey listener (daemon thread via pynput)
# ---------------------------------------------------------------------------

_hotkey_listener = None
_active_glow = None


def _start_hotkey_listener() -> None:
    global _hotkey_listener
    from pynput import keyboard

    def on_activate():
        _bridge.trigger.emit()

    _hotkey_listener = keyboard.GlobalHotKeys({config.HOTKEY_COMBINATION: on_activate})
    _hotkey_listener.start()


# ---------------------------------------------------------------------------
# Capture flow (always runs on the Qt main thread)
# ---------------------------------------------------------------------------

_active_overlay = None
_active_hub = None
_main_window = None


def _on_hotkey() -> None:
    global _active_overlay, _active_glow
    if _active_overlay is not None:
        return

    from screen_glow import ScreenGlowOverlay
    _active_glow = ScreenGlowOverlay(accent=config.ACCENT, duration_ms=600, fire_at=1.0)
    _active_glow.play()

    QTimer.singleShot(80, _launch_capture)


def _launch_capture() -> None:
    global _active_overlay
    if _active_overlay is not None:
        return
    from capture_overlay import start_capture
    _active_overlay = start_capture(on_crop=_on_crop, on_cancel=_on_cancel)


def _on_cancel() -> None:
    global _active_overlay
    _active_overlay = None
    if _main_window is not None:
        _main_window.show()
        _main_window.raise_()


def _on_crop(crop, selection_rect) -> None:
    global _active_overlay
    _active_overlay = None

    # Show hub immediately; OCR result will be injected once it finishes
    _show_hub(crop, None, selection_rect)

    def _parse_in_bg():
        import traceback
        try:
            import parser_engine
            result = parser_engine.parse_image(crop)
        except Exception:
            traceback.print_exc()
            result = None
        # Signal crosses the thread boundary safely; _update_hub runs on main thread
        _bridge.ocr_done.emit(result)

    threading.Thread(target=_parse_in_bg, daemon=True).start()


def _show_hub(crop, result, selection_rect) -> None:
    global _active_hub
    from ocr.base import ParseResult
    from action_hub import show_hub

    if result is None:
        result = ParseResult(raw_text="")

    _active_hub = show_hub(crop, result, selection_rect)


def _update_hub(result) -> None:
    global _active_hub
    if _active_hub is None or not _active_hub.isVisible():
        return
    from ocr.base import ParseResult
    if result is None:
        result = ParseResult(raw_text="[OCR failed]")
    _active_hub._result = result
    _active_hub.set_ocr_loading(False)   # stops the timer, sets ocr_elapsed_s
    elapsed = getattr(_active_hub, "ocr_elapsed_s", 0)
    elapsed_str = f"{elapsed:.1f}s"
    if result.raw_text and result.raw_text not in ("", "[OCR failed]"):
        lines = len([ln for ln in result.raw_text.splitlines() if ln.strip()])
        _active_hub._set_status(
            f"Recognised {lines} line{'s' if lines != 1 else ''} in {elapsed_str}"
        )
    else:
        _active_hub._set_status(f"No text found · {elapsed_str}", ok=False)


# ---------------------------------------------------------------------------
# System tray
# ---------------------------------------------------------------------------

def _build_tray(app: QApplication) -> QSystemTrayIcon:
    icon = QIcon(config.LOGO_PATH)
    if icon.isNull():
        icon = QIcon(config.TRAY_ICON_PATH)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip(f"Snippy  ({config.HOTKEY_DISPLAY})")

    menu = QMenu()
    menu.setStyleSheet(f"""
        QMenu {{
            background: {config.SURFACE};
            border: 1px solid {config.BORDER};
            padding: 4px 0px;
            font-size: 13px;
            color: {config.TEXT};
        }}
        QMenu::item {{
            padding: 8px 20px;
        }}
        QMenu::item:selected {{
            background: {config.ACCENT};
            color: #FFFFFF;
        }}
        QMenu::separator {{
            height: 1px;
            background: {config.BORDER};
            margin: 4px 0px;
        }}
    """)

    show_action = QAction("Show Snippy", menu)
    show_action.triggered.connect(_show_main_window)
    menu.addAction(show_action)

    capture_action = QAction(f"Capture  ({config.HOTKEY_DISPLAY})", menu)
    capture_action.triggered.connect(lambda: QTimer.singleShot(0, _on_hotkey))
    menu.addAction(capture_action)

    menu.addSeparator()

    quit_action = QAction("Quit Snippy", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(_tray_activated)
    tray.show()
    return tray


def _show_main_window() -> None:
    if _main_window is not None:
        _main_window.show()
        _main_window.raise_()
        _main_window.activateWindow()


def _tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        _show_main_window()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Tell Windows to treat this process as a standalone app on the Taskbar
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Snippy.DesktopApp.1.0")
        except Exception:
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Snippy")
    app.setWindowIcon(QIcon(config.LOGO_PATH))

    # Build main window first so it's ready before tray notification
    global _main_window
    from main_window import MainWindow
    _main_window = MainWindow(capture_fn=_on_hotkey)
    _main_window.show()

    tray = _build_tray(app)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[snippy] Warning: system tray not available.")

    # Wire signals to main-thread handlers
    _bridge.trigger.connect(_on_hotkey)
    _bridge.ocr_done.connect(_update_hub)

    t = threading.Thread(target=_start_hotkey_listener, daemon=True)
    t.start()

    # Pre-warm OCR backend in background so first capture is instant
    threading.Thread(target=config.get_backend, daemon=True).start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
