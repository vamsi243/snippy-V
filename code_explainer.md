# Snippy — Code Explainer

A complete walkthrough of the codebase for new developers, followed by step-by-step deployment instructions.

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Data flow](#2-data-flow)
3. [File-by-file breakdown](#3-file-by-file-breakdown)
   - [config.py](#31-configpy)
   - [main.py](#32-mainpy)
   - [main_window.py](#33-main_windowpy)
   - [capture_overlay.py](#34-capture_overlaypy)
   - [action_hub.py](#35-action_hubpy)
   - [screen_glow.py](#36-screen_glowpy)
   - [parser_engine.py](#37-parser_enginepy)
   - [ocr/base.py](#38-ocrbasepy)
   - [ocr/rapidocr_backend.py](#39-ocrrapidocr_backendpy)
   - [ocr/tables.py](#310-ocrtablespy)
   - [ocr/tesseract.py](#311-ocrtesseractpy)
4. [Key design patterns](#4-key-design-patterns)
5. [Deployment — build and distribute](#5-deployment--build-and-distribute)

---

## 1. Architecture overview

```
┌─────────────────────────────────────────────────────┐
│                    main.py                          │
│  QApplication · MainWindow · SystemTray · Bridge   │
│                                                     │
│  pynput thread ──Signal──► main thread              │
│  OCR thread    ──Signal──► main thread              │
└────────────┬──────────────────────────┬────────────┘
             │                          │
    ┌────────▼────────┐      ┌──────────▼──────────┐
    │ capture_overlay │      │     action_hub       │
    │  Full-desktop   │      │  Preview + 5 buttons │
    │  freeze + drag  │      │  + OCR timer         │
    └────────┬────────┘      └──────────┬───────────┘
             │ PIL crop                 │ calls
             ▼                         ▼
    ┌─────────────────┐     ┌──────────────────────┐
    │  parser_engine  │     │   config.py           │
    │  OCR → table    │     │   All constants +     │
    │  → CSV/PDF/URL  │     │   backend factory     │
    └────────┬────────┘     └──────────────────────┘
             │
    ┌────────▼────────────────────────────┐
    │  ocr/                               │
    │  base.py · rapidocr_backend.py      │
    │  tables.py · tesseract.py           │
    └─────────────────────────────────────┘
```

**Thread model**

| Thread | What it does |
|---|---|
| Qt main thread | All UI rendering, signal handling, window management |
| pynput daemon thread | Listens for global hotkey; emits `_bridge.trigger` signal |
| OCR daemon thread | Runs `parser_engine.parse_image()`; emits `_bridge.ocr_done` signal |

Signals are the only safe bridge between threads and Qt. Never touch a QWidget from a background thread.

---

## 2. Data flow

```
User presses Ctrl+Shift+S
        │
        ▼
pynput thread: _bridge.trigger.emit()
        │ (Qt queued connection)
        ▼
Qt main thread: _on_hotkey()
        │
        ├─► ScreenGlowOverlay.play()   ← edge-glow animation
        │
        └─► QTimer(80ms) → _launch_capture()
                │
                ▼
          CaptureOverlay.show()   ← full-desktop freeze-frame
                │
        user drags a rectangle
                │
                ▼
          crop_ready signal emits (PIL.Image, QRect)
                │
                ▼
          _on_crop(crop, selection_rect)
                │
                ├─► show_hub(crop, empty_result, rect)  ← hub appears immediately
                │         ActionHub shows preview + disabled text buttons
                │         status: "Recognising text… 0s"  (1s tick timer starts)
                │
                └─► threading.Thread → _parse_in_bg()
                          │  (OCR runs here — may take 1-3 seconds)
                          │
                          ▼
                    _bridge.ocr_done.emit(result)
                          │ (Qt queued connection)
                          ▼
                    Qt main thread: _update_hub(result)
                          │
                          └─► hub._result = result
                              hub.set_ocr_loading(False)  ← tick timer stops
                              status: "Recognised 3 lines in 1.9s"
                              Copy Text + Search buttons re-enabled
```

---

## 3. File-by-file breakdown

### 3.1 `config.py`

**Purpose:** Single source of truth for every constant, colour token, path, and the OCR backend factory. Nothing is hardcoded in UI files.

```python
# ── Theme tokens ──────────────────────────────────────────────────────
BG = "#EDEAE4"          # warm off-white — matches the logo background
SURFACE = "#FFFFFF"      # white cards / panels
ACCENT = "#1A1A1A"       # near-black — the logo's ink colour
ACCENT_HOVER = "#3A3A3A"
TEXT = "#1A1A1A"
MUTED = "#6B6B6B"        # secondary text (hints, status)
BORDER = "#C8C5C0"       # dividers and outlines
```

```python
# ── Paths ─────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).parent
ASSETS_DIR = APP_DIR / "assets"
LOGO_PATH = str(ASSETS_DIR / "logo.png")
TRAY_ICON_PATH = str(ASSETS_DIR / "tray_icon.png")
```

```python
# ── Backend factory (singleton) ────────────────────────────────────────
_backend_instance = None

def get_backend():
    """Returns the same backend object on every call (lazy init)."""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance
    # Falls back from Tesseract → RapidOCR if Tesseract isn't installed
    from ocr.rapidocr_backend import RapidOcrBackend
    _backend_instance = RapidOcrBackend()
    return _backend_instance
```

**HUB_QSS** is a Qt Style Sheet string (CSS for Qt) applied to the action hub container. It styles `QWidget`, `QPushButton`, and `QLabel` elements by name.

---

### 3.2 `main.py`

**Purpose:** Application entry point. Owns the event loop, the thread-safe signal bridge, the system tray, and all top-level state variables.

#### Signal bridge

```python
class _Bridge(QObject):
    trigger = Signal()       # hotkey thread → main thread
    ocr_done = Signal(object)  # OCR thread → main thread (carries ParseResult)

_bridge = _Bridge()
```

Signals are Qt's thread-safe communication channel. A `Signal.emit()` on any thread delivers the call to the receiving thread's event queue — no mutexes needed.

#### Capture flow functions

```python
def _on_hotkey() -> None:
    """Called on the Qt main thread when the global hotkey fires."""
    # 1. Play the edge-glow animation
    # 2. Wait 80ms (so glow renders first)
    # 3. Launch the capture overlay

def _on_crop(crop, selection_rect) -> None:
    """Called when the user releases the mouse after drawing a selection."""
    _show_hub(crop, None, selection_rect)   # hub appears immediately
    threading.Thread(target=_parse_in_bg, daemon=True).start()  # OCR in background

def _update_hub(result) -> None:
    """Connected to _bridge.ocr_done — runs on main thread."""
    _active_hub._result = result
    _active_hub.set_ocr_loading(False)   # re-enables buttons, stops timer
```

#### Why `daemon=True` on the OCR thread?

A daemon thread is killed automatically when the main thread exits. Without it, closing Snippy would hang until OCR finishes. Daemon threads are safe here because `_bridge.ocr_done` is the only shared state, and Qt signals handle the synchronisation.

---

### 3.3 `main_window.py`

**Purpose:** The primary desktop window that opens on launch. Provides a visual home base with the logo and a Capture button.

```python
class MainWindow(QMainWindow):
    def __init__(self, capture_fn) -> None:
        super().__init__()
        self._capture_fn = capture_fn   # injected — avoids circular import
        self._setup_window()
        self._build_ui()
```

**Dependency injection** (`capture_fn`): `MainWindow` doesn't import `main.py`. Instead, `main.py` passes `_on_hotkey` as a callable when constructing the window. This keeps the dependency graph clean.

```python
def _on_capture_clicked(self) -> None:
    self.hide()   # hide FIRST so the window isn't in the screenshot
    QTimer.singleShot(150, self._capture_fn)  # small delay for hide to take effect
```

```python
def closeEvent(self, event) -> None:
    event.ignore()  # don't close — hide to tray instead
    self.hide()
```

**Layout structure:**

```
QMainWindow
└── QWidget (central)
    └── QVBoxLayout
        ├── QWidget (top_bar) — 6px black accent stripe
        ├── QWidget (content) — logo, instruction text, capture button, hint label
        └── QWidget (footer)  — status label + "Closing hides to tray" note
```

---

### 3.4 `capture_overlay.py`

**Purpose:** Takes a frozen full-desktop screenshot, displays it as a full-screen widget, and lets the user drag a selection rectangle over it.

#### Grabbing the desktop

```python
def grab_full_desktop() -> tuple[Image.Image, QRect]:
    with mss.mss() as sct:
        mon = sct.monitors[0]   # index 0 = combined virtual desktop (all monitors)
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    # virtual_rect is in logical pixels (DPI-scaled)
    union = QRect()
    for screen in app.screens():
        union = union.united(screen.geometry())
    return img, union
```

`mss` returns physical pixels; Qt uses logical pixels. The overlay stores both and applies a scale factor when cropping so the final `PIL.Image` is always at physical (true) pixel resolution.

#### Pixel-accurate crop

```python
def _make_crop(self, sel_local: QRect) -> tuple[Image.Image, QRect]:
    scale_x = snap_w / virt_w   # physical / logical
    scale_y = snap_h / virt_h
    # Convert logical selection → physical crop coordinates
    px = int(sel_local.x() * scale_x)
    py = int(sel_local.y() * scale_y)
    ...
    crop = self._snapshot.crop((px, py, px + pw, py + ph))
```

#### Converting PIL → QPixmap (safe)

```python
def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img = img.convert("RGBA")
    w, h = img.size
    raw = img.tobytes("raw", "RGBA")
    qimg = QImage(raw, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())  # .copy() makes Qt own the buffer
```

The `.copy()` call is critical: `QImage` holds a non-owning pointer to `raw`. Calling `.copy()` before returning makes Qt do a deep copy of the pixel data, so `raw` can be garbage-collected safely.

---

### 3.5 `action_hub.py`

**Purpose:** The floating panel shown after a capture. Contains the preview thumbnail, five action buttons, a status bar, and an OCR progress timer.

#### Window flags

```python
super().__init__(
    parent,
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Window,   # NOT Tool — Tool windows don't reliably receive clicks on Windows
)
```

`Tool` windows on Windows lack proper focus handling. Using `Window` ensures all mouse events are delivered correctly.

#### OCR loading state

```python
def set_ocr_loading(self, loading: bool) -> None:
    for btn in (self._btn_copy_text, self._btn_search):
        btn.setEnabled(not loading)
        btn.setStyleSheet(self._LOADING_BTN_STYLE if loading else self._NORMAL_BTN_STYLE)

    if loading:
        self._ocr_start = time.monotonic()
        self._ocr_tick_timer = QTimer(self)
        self._ocr_tick_timer.setInterval(1000)   # tick every second
        self._ocr_tick_timer.timeout.connect(self._ocr_tick)
        self._ocr_tick_timer.start()
        self._refresh_ocr_status()   # show "Recognising text… 0s" immediately
    else:
        self._ocr_tick_timer.stop()
        self.ocr_elapsed_s = time.monotonic() - self._ocr_start
```

#### Button wiring (direct references)

```python
# Good — store named references to each button
self._btn_copy_image = self._make_btn("📋  Copy Image", "...")
self._btn_copy_text  = self._make_btn("📝  Copy Text",  "...")
# ...
self._btn_copy_image.clicked.connect(self._copy_image)
self._btn_copy_text.clicked.connect(self._copy_text)
```

This is more reliable than collecting buttons by scanning the layout after construction (which can break if the layout order ever changes).

#### Auto-close timer

```python
self._auto_close = QTimer(self)
self._auto_close.setSingleShot(True)
self._auto_close.timeout.connect(self.close)
self._auto_close.start(30000)   # 30 seconds
```

Every button action calls `self._reset_timer()` to restart the 30-second window.

---

### 3.6 `screen_glow.py`

**Purpose:** A brief full-desktop edge-glow animation that plays when the hotkey fires, giving visual feedback before the overlay appears.

```python
class ScreenGlowOverlay(QWidget):
    """Click-through transparent overlay covering all screens."""
    def __init__(self, accent="#1A1A1A", duration_ms=600, fire_at=1.0):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,  # clicks pass through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
```

`WindowTransparentForInput` makes the overlay invisible to mouse events — all clicks go through to whatever is below it.

The animation runs at ~60 fps via a `QTimer(interval=16)`. Each tick updates `self._progress` (0→1), which drives:
- **Alpha envelope** — bloom in, hold, fade out
- **Edge gradients** — `QLinearGradient` on all four edges
- **Sweep highlight** — a bright spot travelling around the screen perimeter

---

### 3.7 `parser_engine.py`

**Purpose:** Coordinates the full OCR pipeline and provides export/search functions. This is a pure-function module — no Qt, no state.

```python
def parse_image(pil_image: Image.Image) -> ParseResult:
    backend = config.get_backend()
    raw_text, lines = backend.recognize(pil_image)   # returns text + bounding boxes

    table = []
    if lines:
        table = reconstruct_geometric(lines)    # Tier 1: geometric clustering
        # Tier 2: RapidTable (optional, only if ENABLE_RAPID_TABLE=1)

    return ParseResult(raw_text=raw_text, lines=lines, table=table, ...)
```

```python
def export_csv(table: list[list[str]], path: str) -> None:
    import pandas as pd
    pd.DataFrame(table).to_csv(path, index=False, header=False)

def export_pdf(result: ParseResult, path: str) -> None:
    # Uses reportlab to write text paragraphs and an optional table
    ...

def search_brave(text: str) -> None:
    url = "https://search.brave.com/search?q=" + urllib.parse.quote_plus(text[:2000])
    config.open_brave(url)   # opens Brave if installed, otherwise default browser
```

---

### 3.8 `ocr/base.py`

**Purpose:** Defines the shared data structures and the `OCRBackend` protocol (interface) that all backends must satisfy.

```python
@dataclass
class TextLine:
    text: str
    bbox: tuple[int, int, int, int]   # x, y, width, height in crop pixels
    confidence: float

@dataclass
class ParseResult:
    raw_text: str
    lines: list[TextLine] = field(default_factory=list)
    table: list[list[str]] = field(default_factory=list)   # rows × cols
    backend: str = ""
    table_strategy: str = ""

class OCRBackend(Protocol):
    """Any class with these two methods can be used as a backend."""
    name: str
    def is_available(self) -> bool: ...
    def recognize(self, image: Image.Image) -> tuple[str, list[TextLine]]: ...
```

Using `Protocol` (structural subtyping) means backends don't need to inherit from a base class — they just need to have the right methods. This makes it easy to add new backends.

---

### 3.9 `ocr/rapidocr_backend.py`

**Purpose:** Wraps RapidOCR (the default OCR engine). RapidOCR uses ONNX models and runs fully on-device with no system binary.

```python
class RapidOcrBackend:
    name = "rapidocr"

    def _init(self) -> None:
        from rapidocr import RapidOCR
        self._engine = RapidOCR()   # downloads models on first call

    def recognize(self, image: Image.Image) -> tuple[str, list[TextLine]]:
        img_array = np.array(image.convert("RGB"))
        result = self._engine(img_array, return_word_box=True)

        # RapidOCR 3.x returns an object with .boxes / .txts / .scores attributes
        # Older versions return a list of (box, text, score) tuples — both handled
        boxes = getattr(result, "boxes", None)
        ...
        items.sort(key=lambda t: centre(t[0]))   # sort top-to-bottom, left-to-right

        for box, txt, score in items:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append(TextLine(
                text=str(txt),
                bbox=(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)),
                confidence=float(score),
            ))
        return "\n".join(ln.text for ln in lines), lines
```

---

### 3.10 `ocr/tables.py`

**Purpose:** Converts a flat list of `TextLine` objects (each with a bounding box) into a 2-D table structure by inferring rows and columns from spatial positions.

#### Tier 1 — Geometric reconstruction

```python
def reconstruct_geometric(lines: list[TextLine]) -> list[list[str]]:
    # Step 1: cluster lines into rows by vertical centre position
    med_h = statistics.median([ln.bbox[3] for ln in lines])
    row_gap = max(med_h * 0.6, 4)   # within 60% of median height → same row

    # Step 2: find column boundaries by clustering x-start positions
    all_x = [ln.bbox[0] for ln in lines]
    col_boundaries = _cluster_column_starts(all_x, gap_factor=0.8 * med_h)

    # Step 3: assign each text fragment to the nearest column
    for row in rows:
        cells = [""] * n_cols
        for ln in row:
            col_idx = _nearest_col(ln.bbox[0], col_boundaries)
            cells[col_idx] = ln.text
        table.append(cells)
```

This works well for clearly-structured tables. For complex tables with merged cells, the optional Tier 2 (RapidTable) handles them via an ML-based approach.

---

### 3.11 `ocr/tesseract.py`

**Purpose:** Optional Tesseract backend for users who already have Tesseract installed and prefer it over RapidOCR.

```python
class TesseractBackend:
    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def recognize(self, image: Image.Image) -> tuple[str, list[TextLine]]:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        # Groups words into lines using block_num + par_num + line_num
        ...
```

Enabled via `SNIPPY_OCR_BACKEND=tesseract`. `config.get_backend()` tries Tesseract first and falls back to RapidOCR if it's not available.

---

## 4. Key design patterns

### Thread safety via Signals
All communication from background threads to Qt goes through `Signal.emit()`. Never call Qt methods directly from a non-main thread.

```python
# WRONG — calling Qt from a background thread
QTimer.singleShot(0, lambda: hub._result = result)   # unsafe

# RIGHT — use a Signal connected on the main thread
_bridge.ocr_done.emit(result)   # thread-safe
# connected to: _bridge.ocr_done.connect(_update_hub)  (main thread)
```

### Lazy initialisation
The OCR backend (`RapidOcrBackend`) is only created on the first capture. This avoids blocking the startup sequence.

### Dependency injection
`MainWindow` receives `capture_fn` as a constructor argument rather than importing `main.py` directly. This prevents circular imports and makes the window independently testable.

### No inheritance for shared logic
Both `action_hub.py` and `capture_overlay.py` have their own `pil_to_qpixmap` function. Sharing via a helper module would create a dependency between two otherwise independent UI layers.

---

## 5. Deployment — build and distribute

### Step 1 — Install PyInstaller

```bash
.venv\Scripts\activate
pip install pyinstaller
```

### Step 2 — Create the spec file

Run once to generate a base spec:

```bash
pyinstaller --name Snippy --windowed --icon assets\logo.png main.py
```

Then open `Snippy.spec` and add the data files and hidden imports:

```python
# Snippy.spec
a = Analysis(
    ['main.py'],
    datas=[
        ('assets', 'assets'),           # logo.png, tray_icon.png
        ('ocr', 'ocr'),                 # OCR module
    ],
    hiddenimports=[
        'rapidocr',
        'onnxruntime',
        'pynput.keyboard',
        'pynput.mouse',
        'PIL._tkinter_finder',
        'lxml._elementpath',
    ],
    ...
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Snippy',
    windowed=True,           # no console window
    icon='assets\\logo.png',
    onefile=True,            # single .exe output
)
```

### Step 3 — Build the exe

```bash
pyinstaller Snippy.spec
```

Output: `dist\Snippy.exe` — a standalone single-file executable. No Python installation needed on the target machine.

### Step 4 — Test the exe

```bash
dist\Snippy.exe
```

Check that:
- The main window opens with the logo
- The hotkey `Ctrl+Shift+S` works
- A capture and OCR cycle completes successfully

> **Common issue:** RapidOCR model files need to be bundled correctly. If you see a model-not-found error, add the models path to `datas` in the spec file:
> ```python
> ('path\to\.venv\Lib\site-packages\rapidocr\models', 'rapidocr\models')
> ```

---

### Step 5 — Create a Windows installer with Inno Setup

[Inno Setup](https://jrsoftware.org/isinfo.php) is free and creates a standard Windows `.exe` installer.

1. Download and install Inno Setup from [jrsoftware.org](https://jrsoftware.org/isinfo.php)
2. Create `installer.iss`:

```ini
[Setup]
AppName=Snippy
AppVersion=1.0.0
AppPublisher=Your Name
DefaultDirName={autopf}\Snippy
DefaultGroupName=Snippy
OutputBaseFilename=Snippy-Setup-1.0.0
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\logo.png
UninstallDisplayIcon={app}\Snippy.exe

[Files]
Source: "dist\Snippy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Snippy"; Filename: "{app}\Snippy.exe"
Name: "{commondesktop}\Snippy"; Filename: "{app}\Snippy.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\Snippy.exe"; Description: "Launch Snippy"; Flags: nowait postinstall skipifsilent
```

3. Open the `.iss` file in Inno Setup IDE and click **Compile**
4. Output: `Snippy-Setup-1.0.0.exe` — a professional installer with Start Menu shortcut and optional desktop icon

---

### Step 6 — Publish on GitHub Releases

GitHub Releases is the simplest way to distribute a Windows app publicly.

1. Create a GitHub repository and push your source code
2. Tag a release:
```bash
git tag v1.0.0
git push origin v1.0.0
```
3. Go to your repo → **Releases** → **Draft a new release**
4. Set the tag to `v1.0.0`, write release notes
5. Upload both files as assets:
   - `Snippy.exe` — portable (no install needed)
   - `Snippy-Setup-1.0.0.exe` — installer
6. Click **Publish release**

Users visit the Releases page and download either file. Direct download link format:
```
https://github.com/your-username/snippy/releases/latest/download/Snippy.exe
```

---

### Step 7 — Publish to the Microsoft Store (MSIX)

The Microsoft Store requires MSIX packaging. This is more involved but gives you discovery, automatic updates, and a trusted install experience.

#### 7a — Package as MSIX with MSIX Packaging Tool

1. Install the **MSIX Packaging Tool** from the Microsoft Store (free)
2. Run it, choose **Create package from existing installer**
3. Select your `Snippy-Setup-1.0.0.exe`
4. Fill in the package identity fields:
   - **Package name:** `YourName.Snippy`
   - **Publisher:** `CN=Your Name` (must match your Partner Center certificate)
   - **Version:** `1.0.0.0`
5. Complete the wizard → output: `Snippy_1.0.0.0_x64.msix`

#### 7b — Enroll in Microsoft Partner Center

1. Go to [partner.microsoft.com](https://partner.microsoft.com)
2. Create a developer account (one-time $19 fee for individuals)
3. Navigate to **Windows & Xbox** → **Apps and games** → **New product** → **App**

#### 7c — Submit the app

1. In Partner Center, create a new app called **Snippy**
2. Under **Packages**, upload your `.msix` file
3. Fill in:
   - **Description** — what Snippy does
   - **Screenshots** — at least 1 screenshot of the main window (1366×768 or larger)
   - **Category** — Productivity → Utilities & tools
   - **Age rating** — complete the questionnaire (will likely be rated Everyone)
   - **Pricing** — Free
4. Click **Submit to Store**

Microsoft review typically takes 1–3 business days. Once approved, Snippy is searchable in the Microsoft Store and can be installed with one click.

#### 7d — Enable automatic updates

MSIX packages installed from the Store update automatically. For GitHub-distributed builds, add a version check at startup:

```python
# In main.py, after the main window is shown:
def _check_for_update():
    import urllib.request, json
    try:
        url = "https://api.github.com/repos/your-username/snippy/releases/latest"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.load(r)
        latest = data["tag_name"].lstrip("v")
        current = "1.0.0"
        if latest != current:
            _main_window.set_status(f"Update available: v{latest}", ok=True)
    except Exception:
        pass

QTimer.singleShot(3000, _check_for_update)
```

---

### Summary of distribution options

| Method | Effort | Audience | Auto-update |
|---|---|---|---|
| GitHub Releases (portable exe) | Low | Developers / power users | Manual |
| GitHub Releases (installer) | Low | General users | Manual |
| Microsoft Store (MSIX) | Medium | All Windows users | Automatic |
| Winget (Windows Package Manager) | Low (after Store) | CLI / IT users | Via winget |

> **Winget tip:** Once your app is on the Microsoft Store, you can also submit it to [winget-pkgs](https://github.com/microsoft/winget-pkgs) so users can install via `winget install Snippy`.
