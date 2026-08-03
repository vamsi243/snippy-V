# Snippy

<p align="center">
  <img src="assets/logo.png" alt="Snippy Logo" width="260"/>
</p>

<p align="center">
  <b>A fast, intelligent, open-source screen-capture & OCR tool for Windows.</b><br/>
  Capture any desktop region, extract text with neural OCR, parse tables directly into CSV spreadsheets, and search — all from a sleek floating action hub.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/PySide6-6.6%2B-green?logo=qt&logoColor=white"/>
  <img src="https://img.shields.io/badge/OCR-RapidOCR%20ONNX-orange"/>
  <img src="https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white"/>
  <img src="https://img.shields.io/badge/License-MIT-brightgreen.svg"/>
</p>

---

## 🌟 Features

- **Global Hotkey (`Ctrl+Shift+S`)**: Instantly freeze your screen and capture any region from anywhere in Windows without needing focus.
- **On-Device Neural OCR**: Powered by RapidOCR and ONNXRuntime for ultra-fast, local text recognition without sending data to the cloud.
- **Instant Tabular CSV Export**: Automatically detects spatial text alignment and converts screenshot tables into native UTF-8 CSV files (< 1ms export).
- **PDF Export**: Generates beautifully formatted PDF documents containing both extracted text and formatted tabular data.
- **One-Click Web Search**: Instantly opens recognized text as a web search in Brave or your default browser.
- **System Tray Integration**: Operates quietly in the Windows notification area with zero taskbar clutter when minimized.
- **Smooth Visual Feedback**: Features custom edge-glow animations and a floating action hub.

---

## 🎯 Use Cases

- **Data Extraction from Non-Copyable Sources**: Instantly copy text or code from videos, webinars, slide decks, scanned documents, and locked web portals.
- **Converting Screen Tables to Excel / CSV**: Capture financial tables, web dashboards, or data tables from images directly into Excel-ready CSV spreadsheets without manual typing.
- **Rapid Research & Lookup**: Snip unfamiliar terms, code error messages, or foreign text and search them online with a single click.
- **Document Archiving**: Convert snippets of articles, receipts, or data reports into clean PDF files.
- **Accessibility & Translation Preparation**: Extract text from non-selectable graphics for translation tools or screen readers.

---

## 🛠️ Technologies Used

| Technology | Purpose |
|---|---|
| **PySide6 (Qt 6)** | High-performance, DPI-aware desktop GUI framework for native Windows UI elements. |
| **RapidOCR** | On-device deep learning OCR engine using PP-OCR models. |
| **ONNXRuntime** | Cross-platform machine learning inference engine for executing ONNX models on CPU. |
| **mss** | Ultra-fast multi-monitor screen capture library written in C/ctypes. |
| **Pillow (PIL) & NumPy** | High-speed pixel manipulation, image cropping, and array transformations. |
| **ReportLab** | Programmatic PDF document layout and rendering engine. |
| **pynput** | OS-level global keyboard listener daemon thread. |
| **PyInstaller** | Executable builder bundling Python runtime, Qt libraries, and ONNX model files into a single `.exe`. |

---

## 🚀 Quick Start

### Option 1: Download Standalone App (`.exe`)
No Python or installation required.
1. Download `Snippy.exe` from the [Releases](https://github.com/vamsi243/snippy-V/releases) page.
2. Double-click `Snippy.exe` to run. Snippy sits in your system tray—press **Ctrl+Shift+S** to capture!

### Option 2: Run from Source

```bash
# 1. Clone the repository
git clone https://github.com/vamsi243/snippy-V.git
cd snippy-V

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell / cmd

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch application
python main.py
```

---

## 📦 Building Standalone Executable (`.exe`)

To package Snippy into a single standalone `.exe` file including pre-warmed ONNX models:

```powershell
# Install PyInstaller
.venv\Scripts\python.exe -m pip install pyinstaller

# Build using the custom spec file
.venv\Scripts\pyinstaller.exe Snippy.spec --noconfirm
```

The output executable will be created at `dist\Snippy.exe`.

---

## 📂 Project Structure

```
snippy/
├── main.py               # Application entry point: QApplication, tray icon, hotkey listener
├── main_window.py        # Primary desktop window (logo header, capture trigger)
├── capture_overlay.py    # Multi-monitor desktop freeze-frame & selection overlay
├── action_hub.py         # Floating hub: thumbnail preview, action buttons, OCR status
├── screen_glow.py        # Animated edge-glow feedback on hotkey press
├── parser_engine.py      # OCR orchestration, fast CSV/PDF export, browser lookup
├── config.py             # Theme tokens, global constants, backend singleton
├── Snippy.spec           # PyInstaller build spec bundling ONNX models & Qt assets
├── ocr/
│   ├── base.py              # TextLine & ParseResult dataclasses, OCRBackend protocol
│   ├── rapidocr_backend.py  # RapidOCR engine wrapper
│   ├── tables.py            # Geometric table reconstruction algorithms
│   └── tesseract.py         # Optional Tesseract OCR fallback
└── assets/
    ├── logo.png             # Application logo & window icon
    └── tray_icon.png        # Windows system tray icon
```

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.
