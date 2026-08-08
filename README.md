# Snippy

Snippy is a Windows screen-capture, OCR, pixel inspection, and AI-agent workflow utility built with Python, PySide6, MSS, RapidOCR, ONNX Runtime, and FastMCP.

It can be used in two ways:

- As a desktop app: capture screenshots with a hotkey, copy OCR text, export tables, pick colors, and measure regions.
- As an MCP server: let AI agents inspect the current screen, measure UI elements, sample colors, run OCR, and record multi-step workflows.

The packaged release is a standalone executable:

```text
dist\Snippy.exe
```

No Python install is required to run the packaged exe.

---

## Features

- Global hotkey: `Ctrl+Shift+S`
- Multi-monitor capture with mixed-DPI coordinate mapping
- OCR with local RapidOCR / ONNX Runtime
- Table reconstruction and CSV/PDF export
- Pixel ruler with width, height, center point, perimeter, and aspect ratio
- Color picker with HEX, RGB, HSL, brightness, and contrast ratios
- System tray app with capture, ruler, color picker, and quit actions
- FastMCP server over SSE or stdio
- AI-agent process recorder that saves screenshots, OCR text, `manifest.json`, and `walkthrough.md`

---

## Quick Start With The EXE

1. Download or copy the built executable:

   ```text
   Snippy.exe
   ```

2. Run it:

   ```powershell
   .\Snippy.exe
   ```

3. Snippy opens the desktop app and starts the MCP SSE server automatically:

   ```text
   http://127.0.0.1:8000/sse
   ```

4. Use the tray icon or `Ctrl+Shift+S` to capture.

If Windows SmartScreen warns about the executable, choose the normal "More info" flow only if you trust the file source.

---

## Starting The MCP Server

Snippy supports two MCP transports.

### Option 1: SSE Mode

This is the recommended mode for most AI agents.

Run:

```powershell
V:\Snippy\dist\Snippy.exe
```

The desktop UI starts, and the MCP server listens at:

```text
http://127.0.0.1:8000/sse
```

Use a different port if `8000` is already taken:

```powershell
V:\Snippy\dist\Snippy.exe --mcp-port 8002
```

Disable MCP and run only the desktop app:

```powershell
V:\Snippy\dist\Snippy.exe --no-mcp
```

### Option 2: Stdio Mode

Use stdio when an AI client wants to launch Snippy as a subprocess.

```powershell
V:\Snippy\dist\Snippy.exe --mcp-stdio
```

In this mode Snippy does not open the desktop UI. It runs as a headless MCP process over stdin/stdout.

---

## Add Snippy MCP To AI Agents

Use one of these configurations depending on your client.

### Codex Desktop

Edit:

```text
C:\Users\<you>\.codex\config.toml
```

Add:

```toml
[mcp_servers.snippy]
url = "http://127.0.0.1:8000/sse"
```

Then restart Codex Desktop or open a new Codex task. Existing tasks may not receive newly configured MCP tools until they are restarted.

For a custom port:

```toml
[mcp_servers.snippy]
url = "http://127.0.0.1:8002/sse"
```

### Claude Desktop

Edit `claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "snippy": {
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

Restart Claude Desktop after changing the config.

### Cursor / VS Code MCP Clients

Most MCP clients accept either an SSE URL or a stdio command.

SSE:

```json
{
  "mcpServers": {
    "snippy": {
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

Stdio:

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

Use stdio when you want the AI client to start and stop Snippy automatically. Use SSE when you want Snippy to stay running in the tray for both manual captures and agent tools.

---

## Test MCP

### Check the server is listening

```powershell
netstat -ano | findstr :8000
```

Expected: a `LISTENING` entry for `127.0.0.1:8000`.

### Try these prompts in your AI agent

```text
Use the snippy MCP and call snippy_get_monitor_layout.
```

```text
Use snippy MCP to measure region x1=10 y1=20 x2=110 y2=70.
```

```text
Use snippy MCP to sample the color at x=450 y=120.
```

Expected examples:

- `snippy_get_monitor_layout` returns monitor count, virtual desktop bounds, logical rectangles, physical rectangles, and DPI scale factors.
- `snippy_measure_region` returns dimensions, aspect ratio, center point, and perimeter.
- `snippy_pick_color` returns HEX, RGB, HSL, brightness, and contrast against white/black.

### Troubleshooting log

Snippy writes MCP diagnostics here:

```text
captures\snippy_mcp.log
```

When running from `dist\Snippy.exe`, process recording output may be created under:

```text
dist\captures\
```

Check the log if the tray app opens but the MCP endpoint does not respond.

---

## MCP Tools

| Tool | Parameters | Description |
|---|---|---|
| `snippy_take_snip` | `region?: [x1, y1, x2, y2]` | Captures the full screen or a region as an image payload. |
| `snippy_ocr_screen` | `region?: [x1, y1, x2, y2]` | Runs OCR and returns extracted text. |
| `snippy_extract_table` | `region?: [x1, y1, x2, y2]` | Extracts table-like text into rows and CSV. |
| `snippy_pick_color` | `x: int, y: int` | Samples a pixel color and returns HEX/RGB/HSL/contrast. |
| `snippy_get_color_palette` | `region?: [x1, y1, x2, y2], max_colors?: int` | Returns dominant colors in a region. |
| `snippy_measure_region` | `x1, y1, x2, y2` | Measures width, height, aspect ratio, center, and perimeter. |
| `snippy_get_monitor_layout` | none | Returns virtual desktop and monitor geometry. |
| `snippy_start_process_session` | `session_name: str` | Starts a process recording folder. |
| `snippy_record_step` | `step_name: str, description: str, region?: [x1, y1, x2, y2]` | Captures a step image and logs OCR metadata. |
| `snippy_finish_process_session` | none | Finalizes and returns the recorded walkthrough. |

---

## Agent Workflow Examples

### Design Audit

```text
Use Snippy MCP to sample the primary button color at x=450 y=120 and measure the button region from x1=200 y1=300 x2=500 y2=360.
```

### Screen OCR

```text
Use Snippy MCP to OCR the current screen and summarize the visible error message.
```

### Process Recording

```text
Use Snippy MCP to start a process session named checkout_test, record the cart page, record the shipping form, then finish the session.
```

---

## Run From Source

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Run from source with a custom MCP port:

```powershell
python main.py --mcp-port 8002
```

Run source stdio MCP:

```powershell
python main.py --mcp-stdio
```

---

## Build Standalone EXE

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\pyinstaller.exe Snippy.spec --noconfirm
```

Output:

```text
dist\Snippy.exe
```

The current full-feature build bundles PySide6, FastMCP, RapidOCR, ONNX Runtime, image processing, table/export libraries, and Windows support DLLs. This makes the exe relatively large, but it keeps the app portable.

---

## Size And Performance Notes

The current exe is intentionally full-featured and self-contained. It is heavy mainly because it bundles:

- PySide6 / Qt for the desktop UI
- RapidOCR and ONNX Runtime for offline OCR
- FastMCP, MCP protocol libraries, Uvicorn, Starlette, and related HTTP/SSE dependencies
- OpenCV/Numpy/Pandas/ReportLab/LXML-style support libraries used by OCR, image processing, tables, CSV, and PDF export

Safe future optimizations:

- Build a second "lite" variant without MCP for users who only need manual screen capture.
- Build a second "agent" variant without PDF/table export if only MCP screen inspection is needed.
- Convert to one-folder PyInstaller mode for faster startup and easier DLL inspection, while keeping functionality.
- Tighten PyInstaller hidden imports to collect fewer optional FastMCP/jsonschema test/CLI modules after a careful regression pass.
- Lazy-load OCR and export libraries so app startup stays light even if the full exe remains large.

Avoid removing OCR, ONNX Runtime, PySide6, or FastMCP from the main build unless you intentionally remove those features.

---

## License

MIT. See `LICENSE`.
