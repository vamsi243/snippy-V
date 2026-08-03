"""Central configuration: hotkeys, theme, paths, OCR backend selection, platform helpers."""

import os
import sys
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------
PLATFORM = sys.platform  # "win32" | "darwin" | "linux"
IS_WIN = PLATFORM == "win32"
IS_MAC = PLATFORM == "darwin"

# ---------------------------------------------------------------------------
# Hotkey  (pynput Key combo)
# ---------------------------------------------------------------------------
HOTKEY_COMBINATION = "<ctrl>+<shift>+s"
HOTKEY_DISPLAY = "Ctrl+Shift+S"

# ---------------------------------------------------------------------------
# Theme — based on Snippy logo: near-black on warm off-white
# ---------------------------------------------------------------------------
BG = "#EDEAE4"          # warm off-white (logo background colour)
SURFACE = "#FFFFFF"      # white panels / cards
ACCENT = "#1A1A1A"       # near-black (logo ink colour)
ACCENT_HOVER = "#3A3A3A" # dark grey hover
TEXT = "#1A1A1A"         # body text
MUTED = "#6B6B6B"        # secondary / hint text
BORDER = "#C8C5C0"       # subtle divider
SUCCESS = "#2D7A50"      # confirmation green
WARNING = "#B5760A"      # amber
ERROR = "#C0392B"        # error red

CORNER_RADIUS = 10
BUTTON_PADDING = "9px 16px"

HUB_QSS = f"""
QWidget#hub_container {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {CORNER_RADIUS}px;
}}
QPushButton {{
    background: transparent;
    color: {TEXT};
    border: none;
    border-radius: 6px;
    padding: {BUTTON_PADDING};
    font-size: 13px;
    text-align: left;
}}
QPushButton:hover {{
    background: {ACCENT};
    color: #FFFFFF;
}}
QPushButton:pressed {{
    background: {ACCENT_HOVER};
    color: #FFFFFF;
}}
QLabel#status_label {{
    color: {MUTED};
    font-size: 11px;
    padding: 2px 6px;
}}
"""

# ---------------------------------------------------------------------------
# OCR backend selection
# ---------------------------------------------------------------------------
# "rapidocr" (default) or "tesseract" (requires Tesseract binary installed)
OCR_BACKEND = os.environ.get("SNIPPY_OCR_BACKEND", "rapidocr")

# Optional path to Tesseract binary (only needed if not on PATH)
TESSERACT_CMD: str | None = os.environ.get("TESSERACT_CMD", None)

# ---------------------------------------------------------------------------
# Table strategy
# ---------------------------------------------------------------------------
# "geometric" | "rapid_table" | "auto"
TABLE_STRATEGY = os.environ.get("SNIPPY_TABLE_STRATEGY", "geometric")
ENABLE_RAPID_TABLE = os.environ.get("SNIPPY_ENABLE_RAPID_TABLE", "0") == "1"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
ASSETS_DIR = APP_DIR / "assets"
TRAY_ICON_PATH = str(ASSETS_DIR / "tray_icon.png")
LOGO_PATH = str(ASSETS_DIR / "logo.png")

# ---------------------------------------------------------------------------
# Brave browser path resolver
# ---------------------------------------------------------------------------

def find_brave() -> str | None:
    """Return the path to the Brave executable, or None if not found."""
    if IS_WIN:
        candidates = []
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env_var, "")
            if base:
                candidates.append(
                    Path(base) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
                )
        for path in candidates:
            if path.exists():
                return str(path)
        return None

    if IS_MAC:
        mac_paths = [
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
            Path.home() / "Applications" / "Brave Browser.app" / "Contents" / "MacOS" / "Brave Browser",
        ]
        for path in mac_paths:
            if path.exists():
                return str(path)
        return None

    # Linux
    for name in ("brave-browser", "brave"):
        result = subprocess.run(["which", name], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    return None


def open_brave(url: str) -> None:
    """Open url in Brave if available, otherwise fall back to default browser."""
    import webbrowser

    brave = find_brave()
    if brave:
        if IS_MAC:
            subprocess.Popen(["open", "-a", "Brave Browser", url])
        else:
            subprocess.Popen([brave, url])
    else:
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# Backend factory — singleton so the ONNX engine loads only once
# ---------------------------------------------------------------------------

_backend_instance = None


def get_backend():
    """Return the cached OCR backend. Initialises on first call."""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    if OCR_BACKEND == "tesseract":
        from ocr.tesseract import TesseractBackend
        b = TesseractBackend()
        if b.is_available():
            _backend_instance = b
            return _backend_instance
        print("[config] Tesseract not available, falling back to RapidOCR")

    from ocr.rapidocr_backend import RapidOcrBackend
    _backend_instance = RapidOcrBackend()
    return _backend_instance
