# Snippy Code Explainer

This document explains the current Snippy codebase for maintenance and release work.

## Architecture

Snippy is a PySide6 desktop app with four user-facing surfaces:

- `main_window.py`: the compact app window with `+ New`, `Snip`, `Ruler`, and `Color`.
- `capture_overlay.py`: the full-screen capture overlay shown on every monitor.
- `action_hub.py`: the floating post-capture hub with preview, OCR status, and actions.
- `system tray`: created in `main.py` for show/capture/ruler/color/quit commands.

Core service modules:

- `parser_engine.py`: runs OCR, reconstructs tables, exports CSV/PDF, opens search.
- `config.py`: app constants, theme colors, paths, OCR backend singleton, browser helper.
- `ocr/`: backend protocol, RapidOCR adapter, table reconstruction, optional Tesseract.

## Runtime Flow

1. `main.py` enables Windows DPI awareness before creating `QApplication`.
2. `MainWindow` is created and the tray menu is registered.
3. A daemon `pynput` global hotkey listener emits a Qt signal for `Ctrl+Shift+S`.
4. A capture request closes any active Action Hubs, flushes Qt events, plays a short glow,
   and then starts capture.
5. `capture_overlay.start_capture()` grabs one frozen desktop snapshot with `mss`.
6. `CaptureSession` creates one `CaptureOverlay` per monitor.
7. The selected overlay emits a PIL crop plus its global logical selection rectangle.
8. `main.py` opens an `ActionHub` immediately, then OCR runs in a background thread.
9. OCR results are delivered back to the hub through a Qt signal.

## Multi-Monitor Design

The current implementation intentionally avoids one giant spanning overlay window.
Windows mixed-DPI setups can report different coordinate systems for Qt window geometry
and physical screen capture. A spanning window caused the second monitor to render
stretched, offset, or partially covered.

Snippy now uses one overlay window per monitor:

- `grab_full_desktop()` collects Qt screens and the combined `mss` screenshot.
- `_build_screen_map()` pairs each Qt screen with one `mss` monitor.
- Qt screens are sorted by position so repeated captures use a stable order.
- Each map item stores:
  - `log_rect`: Qt logical monitor geometry
  - `rel_log_rect`: logical geometry relative to the virtual desktop
  - `phys_rect`: physical monitor rectangle inside the `mss` snapshot
  - `scale_x` and `scale_y`: physical/logical scale factors
  - `cover_rect`: the Qt window rectangle for that monitor

`CaptureSession` creates one `CaptureOverlay` for each map item. Each overlay is attached
to its matching `QScreen` and shown fullscreen. The overlay paints only that monitor's
portion of the frozen screenshot.

## Capture Math

Mouse events arrive in the local coordinate space of one monitor overlay.

`_local_to_virtual_point()` converts local overlay coordinates to logical virtual-desktop
coordinates. `_logical_to_physical()` then maps that logical point into the physical
`mss` snapshot using the screen's per-axis scale factors.

For normal snips, `_make_crop()`:

1. Converts the selected local rectangle to a virtual logical rectangle.
2. Intersects that rectangle with each screen's logical rectangle.
3. Converts each intersection to physical pixels.
4. Crops the shared `mss` snapshot.
5. Returns a single PIL image plus the global logical selection rectangle.

This is why mixed-DPI monitors, stacked monitors, and monitors positioned left of the
primary screen can work without a global scale guess.

## Modes

Snippy supports three capture modes:

- `snip`: normal rectangular capture.
- `ruler`: draws a measurement rectangle and leaves the overlay open.
- `color`: shows a live color tooltip and copies the clicked pixel as `#RRGGBB`.

Scroll capture has been removed from the active app because stitched captures reduced OCR
quality and made capture behavior less predictable.

## Action Hub

`ActionHub` appears beside the selected region. It owns direct references to all buttons
to avoid Qt object lifetime surprises.

Header actions:

- `+`: start a new normal snip.
- `Scale`: start ruler mode.
- `Color`: start color picker mode.
- `X`: close the hub.

Body actions:

- Copy Image
- Copy Text
- Export CSV
- Export PDF
- Search Text

When a header action starts a new capture, the hub closes first. `main.py` also closes any
remaining active hubs before the next screenshot, so old always-on-top windows are not
captured into the next overlay.

## OCR And Exports

`parser_engine.parse_image()` gets the configured backend from `config.get_backend()`,
runs OCR, and passes recognized text lines to `ocr.tables.reconstruct_geometric()`.

The default backend is RapidOCR. Tesseract exists as an optional fallback when explicitly
selected through `SNIPPY_OCR_BACKEND=tesseract`.

Exports:

- `export_csv()` writes UTF-8-SIG CSV for Excel compatibility.
- `export_pdf()` uses ReportLab to create a simple PDF with text and table output.
- `search_brave()` opens Brave when found, otherwise falls back to the default browser.

## Threading

Qt UI work stays on the main thread. OCR runs in a daemon background thread after the
Action Hub appears. `_Bridge.ocr_done` carries the OCR result and target hub back to the
main thread for UI updates.

## Release Checklist

Before publishing:

1. Recreate a clean virtual environment.
2. Install `requirements.txt`.
3. Run syntax/import checks.
4. Test from source on one monitor.
5. Test from source on two monitors with mixed DPI.
6. Test `Snip`, `Ruler`, `Color`, copy text, copy image, CSV export, PDF export, and search.
7. Build with `Snippy.spec`.
8. Test the built `dist\Snippy.exe` on a clean Windows machine.

Useful local checks:

```powershell
python -m compileall -q .
python -c "import main, main_window, capture_overlay, action_hub, parser_engine; print('imports ok')"
```

## Packaging Notes

`Snippy.spec` includes app assets and dynamically locates the installed `rapidocr` package
so OCR model files are bundled with the executable. Keep the spec in sync with dependency
changes.

Generated folders and files such as `.venv`, `build`, `dist`, `__pycache__`, and ad hoc
test exports should not be committed.
