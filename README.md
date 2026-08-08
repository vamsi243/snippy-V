# Snippy

Snippy is a fast Windows screen-capture and OCR utility built with Python and PySide6.
It captures a selected desktop region, extracts text locally with RapidOCR, reconstructs
simple tables, and lets you copy, export, or search the result from a small floating hub.

## Features

- Global hotkey: `Ctrl+Shift+S`
- Multi-monitor capture with per-monitor DPI handling
- On-device OCR through RapidOCR and ONNX Runtime
- Pixel ruler mode for measuring screen regions
- Color picker mode with click-to-copy hex values
- Copy captured image to clipboard
- Copy recognized text to clipboard
- Export detected tables to CSV
- Export captured text and tables to PDF
- Search recognized text in Brave, with default browser fallback
- System tray operation

## Current UI

The main window has a compact command bar:

- `+ New`: start a normal snip
- `Snip`: capture a screen region
- `Ruler`: measure a region in pixels
- `Color`: pick a pixel color

After a snip, the floating Action Hub shows:

- `+`: start another snip
- `Scale`: open the pixel ruler
- `Color`: open the color picker
- Copy/export/search actions for the captured content

Scroll capture is intentionally disabled because stitched captures produced lower OCR
quality than normal region snips.

## Requirements

- Windows 10 or Windows 11
- Python 3.11+
- A display session with desktop capture permission

## Run From Source

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

If the checked-in virtual environment is stale, recreate it:

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build Standalone EXE

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\pyinstaller.exe Snippy.spec --noconfirm
```

The executable is written to:

```text
dist\Snippy.exe
```

Before publishing, test the built executable on:

- A single monitor
- Two monitors with matching DPI
- Two monitors with mixed DPI, such as 100% plus 125%
- A monitor positioned above, below, left, and right of the primary display

## Project Structure

```text
Snippy/
|-- main.py                # QApplication, tray menu, hotkey, capture flow
|-- main_window.py         # Main app window and command bar
|-- capture_overlay.py     # Multi-monitor overlay, snip, ruler, color picker
|-- action_hub.py          # Floating post-capture hub
|-- screen_glow.py         # Short capture feedback animation
|-- parser_engine.py       # OCR orchestration, CSV/PDF export, web search
|-- config.py              # Theme, constants, backend factory, browser helpers
|-- Snippy.spec            # PyInstaller build configuration
|-- ocr/
|   |-- base.py            # Shared OCR dataclasses and protocol
|   |-- rapidocr_backend.py
|   |-- tables.py
|   `-- tesseract.py       # Optional fallback backend
`-- assets/
    |-- logo.png
    `-- tray_icon.png
```

## Notes For Release

- Do not bundle `.venv`, `build`, `dist`, `__pycache__`, or generated test outputs.
- Keep `assets/logo.png` and `assets/tray_icon.png` available to PyInstaller.
- RapidOCR model files are discovered through the installed `rapidocr` package in
  `Snippy.spec`.
- The app sets Windows DPI awareness before `QApplication` starts. This is important
  for stable multi-monitor capture.

## License

MIT. See `LICENSE`.
