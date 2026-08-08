# Snippy Code Explainer

This document explains the Snippy codebase for maintainers, release builders, and people integrating Snippy with AI agents through MCP.

---

## High-Level Architecture

Snippy has five major surfaces:

- `main.py`: application entry point, CLI flags, tray setup, hotkey wiring, and MCP startup.
- `main_window.py`: compact desktop control window.
- `capture_overlay.py`: multi-monitor screenshot overlay, ruler mode, color picker mode, and crop math.
- `action_hub.py`: post-capture floating hub for copy/export/search actions.
- `mcp_server.py`: FastMCP server exposing Snippy screen-inspection tools to AI agents.

Supporting modules:

- `config.py`: theme constants, app paths, OCR backend selection, Brave browser helper.
- `parser_engine.py`: OCR orchestration, table reconstruction, CSV/PDF export helpers.
- `ocr/base.py`: OCR protocol and parse result structure.
- `ocr/rapidocr_backend.py`: RapidOCR / ONNX Runtime backend.
- `ocr/tesseract.py`: optional Tesseract backend.
- `ocr/tables.py`: geometric table reconstruction.
- `Snippy.spec`: PyInstaller build definition for the standalone exe.
- `Snippy-macOS.spec`: PyInstaller build definition for the experimental macOS `.app`.
- `.github/workflows/build.yml`: GitHub Actions release workflow for Windows and macOS artifacts.
- `scripts/smoke_mcp_stdio.py`: CI smoke test for packaged MCP stdio.

---

## Runtime Flow

1. `main.py` parses flags:
   - `--mcp-stdio`
   - `--mcp-port`
   - `--no-mcp`
2. If `--mcp-stdio` is present, Snippy starts only the FastMCP stdio server and exits the GUI path.
3. Otherwise, Snippy enables Windows DPI awareness and creates the PySide6 `QApplication`.
4. If MCP is enabled, `mcp_server.start_mcp_sse_server()` starts the SSE server in a daemon background thread.
5. `MainWindow` is shown and the system tray menu is built.
6. A daemon `pynput` listener watches `Ctrl+Shift+S`.
7. Capture requests play the glow overlay, launch the capture overlay, and return a PIL crop.
8. The Action Hub appears immediately while OCR runs in a background thread.
9. OCR results are delivered back to the UI through Qt signals.

---

## MCP Startup Modes

### Embedded GUI SSE Mode

Default exe launch:

```powershell
V:\Snippy\dist\Snippy.exe
```

Default source launch:

```powershell
python main.py
```

Result:

```text
http://127.0.0.1:8000/sse
```

Custom port:

```powershell
V:\Snippy\dist\Snippy.exe --mcp-port 8002
python main.py --mcp-port 8002
```

No MCP:

```powershell
V:\Snippy\dist\Snippy.exe --no-mcp
python main.py --no-mcp
```

### Headless Stdio Mode

Packaged exe:

```powershell
V:\Snippy\dist\Snippy.exe --mcp-stdio
```

Source:

```powershell
python main.py --mcp-stdio
```

This mode is used when an AI client starts Snippy as a subprocess and communicates over stdin/stdout.

---

## MCP Client Configuration

### Codex Desktop

`C:\Users\<you>\.codex\config.toml`

```toml
[mcp_servers.snippy]
url = "http://127.0.0.1:8000/sse"
```

Restart Codex Desktop or open a new Codex task after changing this file.

### Claude Desktop / JSON MCP Clients

```json
{
  "mcpServers": {
    "snippy": {
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

### Stdio JSON Config

```json
{
  "mcpServers": {
    "snippy": {
      "command": "V:\\Snippy\\dist\\Snippy.exe",
      "args": ["--mcp-stdio"]
    }
  }
}
```

SSE is best when users want the desktop tray app and agent tools at the same time. Stdio is best when the agent owns the server process lifecycle.

---

## MCP Tool Registry

`mcp_server.py` creates a `FastMCP("Snippy MCP Engine")` instance and registers:

- `snippy_take_snip(region=None)`
- `snippy_ocr_screen(region=None)`
- `snippy_extract_table(region=None)`
- `snippy_pick_color(x, y)`
- `snippy_get_color_palette(region=None, max_colors=5)`
- `snippy_measure_region(x1, y1, x2, y2)`
- `snippy_get_monitor_layout()`
- `snippy_start_process_session(session_name)`
- `snippy_record_step(step_name, description, region=None)`
- `snippy_finish_process_session()`

Most tools call `capture_overlay.grab_full_desktop()` to obtain a fresh screen image and monitor mapping. Region arguments use virtual desktop logical coordinates.

---

## MCP Diagnostics

Packaged windowed apps can hide stdout/stderr. Snippy therefore writes MCP startup diagnostics to:

```text
captures\snippy_mcp.log
```

Important implementation details:

- `mcp_server._log()` writes timestamped errors and tracebacks.
- FastMCP import or server creation failures are logged instead of silently disappearing.
- `_ensure_stdio_handles()` assigns `os.devnull` to `sys.stdout` / `sys.stderr` when PyInstaller windowed mode sets them to `None`.
- This fixes Uvicorn formatter startup crashes in `console=False` builds.

When running from `dist\Snippy.exe`, process-recording output may be written under:

```text
dist\captures\
```

This happens because the exe working directory is commonly `dist`.

---

## Multi-Monitor Capture Design

Snippy avoids a single giant spanning overlay because Windows mixed-DPI setups can report different coordinate systems between Qt and physical screen capture.

`capture_overlay.grab_full_desktop()`:

1. Gets Qt screens from `QApplication`.
2. Captures the combined physical desktop with `mss`.
3. Builds a screen map that pairs each Qt screen with an MSS monitor.
4. Stores logical and physical rectangles plus per-axis scale factors.

Each screen map item includes:

- `log_rect`: Qt logical monitor geometry
- `rel_log_rect`: logical geometry relative to the virtual desktop
- `phys_rect`: physical monitor rectangle in the MSS snapshot
- `scale_x` / `scale_y`: physical-to-logical scaling
- `dpr`: Qt device pixel ratio
- `cover_rect`: overlay window rectangle

`CaptureSession` creates one overlay per monitor. That keeps drawing, mouse events, and cropping aligned on mixed-DPI displays.

---

## Capture Math

Mouse events arrive in local overlay coordinates.

The conversion path is:

```text
local overlay point
-> virtual desktop logical point
-> physical MSS pixel point
```

For a normal crop:

1. Convert the selected local rectangle to a virtual logical rectangle.
2. Intersect it with each screen's logical rectangle.
3. Convert each intersection to physical pixels.
4. Crop from the shared MSS screenshot.
5. Return a final PIL image plus the global logical selection rectangle.

The MCP tools reuse the same screen capture and coordinate mapping logic, so agent measurements align with the desktop UI.

---

## Desktop Modes

Snippy has three capture modes:

- `snip`: normal rectangular screen capture.
- `ruler`: measure a screen region without closing immediately.
- `color`: sample a pixel and copy its HEX code.

The tray menu exposes:

- Show Snippy
- Capture
- Pixel Ruler
- Color Picker
- MCP server status
- Quit Snippy

---

## Action Hub

`ActionHub` appears next to the captured region and keeps direct references to its buttons to avoid Qt lifetime issues.

Header actions:

- `+`: start another snip
- `Scale`: start ruler mode
- `Color`: start color mode
- `X`: close the hub

Body actions:

- Copy Image
- Copy Text
- Export CSV
- Export PDF
- Search Text

OCR runs after the hub appears so the UI feels responsive even when the OCR backend is still warming up.

---

## OCR, Tables, And Exports

`parser_engine.parse_image()` gets the selected backend from `config.get_backend()`.

Default:

```text
SNIPPY_OCR_BACKEND=rapidocr
```

Optional:

```text
SNIPPY_OCR_BACKEND=tesseract
```

Exports:

- `export_csv()` writes UTF-8-SIG CSV for Excel compatibility.
- `export_pdf()` uses ReportLab.
- `search_brave()` opens Brave when found, otherwise uses the default browser.

Table extraction uses geometric reconstruction by default.

---

## Process Recording

The MCP process recorder is managed by `_ACTIVE_SESSION` and `_SESSION_LOCK`.

Flow:

1. `snippy_start_process_session("name")`
   - Creates `captures/process_<name>_<timestamp>/`
   - Initializes `manifest.json`
2. `snippy_record_step("Step Name", "Description", region)`
   - Captures screen or region
   - Saves `step_01_step_name.png`
   - Runs OCR
   - Updates `manifest.json`
   - Updates `walkthrough.md`
3. `snippy_finish_process_session()`
   - Returns the final manifest, walkthrough path, and step list
   - Clears active session state

This feature is useful for QA walkthroughs, bug reproduction, design audits, and onboarding documentation.

---

## Packaging

`Snippy.spec` builds a one-file Windows executable.

`Snippy-macOS.spec` builds an experimental macOS app bundle. macOS capture and hotkey behavior still needs real-device validation because GitHub Actions cannot grant Screen Recording and Accessibility permissions in the same way an end-user Mac does.

The spec bundles:

- `assets/`
- `ocr/`
- RapidOCR package data
- PySide6 / Qt dependencies
- FastMCP and MCP protocol dependencies
- Uvicorn / Starlette / SSE dependencies
- pywin32 runtime hooks
- OCR, image, table, and export libraries

The exe uses:

```python
console=False
```

That is why MCP diagnostics are written to `captures\snippy_mcp.log` instead of relying on a terminal.

---

## Build Commands

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m PyInstaller Snippy.spec --noconfirm
```

Output:

```text
dist\Snippy.exe
```

GitHub Actions release artifacts:

```text
Snippy-Windows-x64.exe
Snippy-macOS-x64.zip
Snippy-macOS-arm64.zip
```

The release workflow smoke-tests packaged MCP stdio by calling `snippy_measure_region`. This verifies the packaged MCP server starts and responds without requiring CI screen-capture permissions.

Recommended validation:

```powershell
python -m py_compile main.py mcp_server.py capture_overlay.py action_hub.py config.py main_window.py parser_engine.py
```

Start the exe and verify default SSE:

```powershell
V:\Snippy\dist\Snippy.exe
netstat -ano | findstr :8000
```

Then use an MCP client to call:

```text
snippy_get_monitor_layout
snippy_measure_region
snippy_pick_color
```

---

## Release Checklist

Before publishing a new exe:

1. Recreate a clean virtual environment.
2. Install `requirements.txt`.
3. Run syntax/import checks.
4. Test desktop UI on one monitor.
5. Test desktop UI on two monitors, especially mixed DPI.
6. Test `Snip`, `Ruler`, `Color`, copy text, copy image, CSV export, PDF export, and search.
7. Test SSE MCP from the exe on the default port.
8. Test SSE MCP from the exe on a custom port.
9. Test stdio MCP from the exe.
10. Confirm `captures\snippy_mcp.log` is empty or contains only expected startup entries.
11. Build with `Snippy.spec`.
12. Build macOS with `Snippy-macOS.spec` if publishing beta macOS artifacts.
13. Test `dist\Snippy.exe` on a clean Windows machine.
14. Test `Snippy.app` on a real Mac with Screen Recording and Accessibility permissions.
15. Add Windows code signing and macOS signing/notarization before treating artifacts as polished public releases.

---

## Size And Efficiency Notes

The current exe is large because it is a full-feature, self-contained Windows app. The biggest contributors are:

- PySide6 / Qt
- RapidOCR and ONNX Runtime
- FastMCP plus HTTP/SSE server dependencies
- OpenCV, NumPy, Pandas, LXML, and ReportLab style dependencies
- Windows support DLLs and PyInstaller bootloader files

Lower-risk improvements:

- Keep the current full build as the default release and add a second "lite" build later.
- Use one-folder PyInstaller builds during testing to improve startup and inspect dependency size.
- Lazy-load OCR/export modules so startup is faster.
- Prune optional FastMCP/jsonschema/test/CLI hidden imports only after MCP regression testing.
- Consider separate variants:
  - `Snippy.exe`: full desktop + OCR + MCP
  - `SnippyLite.exe`: desktop capture + ruler + color, no MCP/OCR
  - `SnippyAgent.exe`: MCP screen tools, no PDF/table export

Do not remove PySide6, FastMCP, RapidOCR, or ONNX Runtime from the current main build unless you intentionally remove the corresponding feature.

---

## Known Operational Notes

- Newly added MCP config usually requires restarting the AI client or opening a new chat/task.
- If another app uses port `8000`, start Snippy with `--mcp-port <port>` and update the MCP client config.
- MCP region coordinates are virtual desktop logical coordinates, not necessarily raw physical pixels on mixed-DPI systems.
- If screen capture returns unexpected geometry, call `snippy_get_monitor_layout` first.
