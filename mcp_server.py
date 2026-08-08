"""FastMCP Server module for Snippy.

Provides tools for AI agents (Gemini Antigravity, Claude, Cursor, VS Code) to:
- Take screenshots and run headless OCR / table extraction
- Sample colors, generate palettes, and calculate contrast ratios
- Measure screen pixel boundaries, aspect ratios, and DPI metrics
- Record multi-step process workflows to dedicated screenshot folders
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple, Dict

from PIL import Image

import config


_LOG_LOCK = threading.Lock()


def _log(message: str, exc: BaseException | None = None) -> None:
    """Write MCP diagnostics somewhere visible for windowed builds."""
    try:
        log_dir = Path.cwd() / "captures"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "snippy_mcp.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _LOG_LOCK, log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
            if exc is not None:
                f.write("".join(traceback.format_exception(exc)))
                f.write("\n")
    except Exception:
        pass


try:
    from fastmcp import FastMCP
except Exception as exc:
    _log("FastMCP import failed; MCP server is unavailable.", exc)
    FastMCP = None

import capture_overlay
import parser_engine


# Initialize FastMCP Server
try:
    mcp = FastMCP("Snippy MCP Engine") if FastMCP else None
except Exception as exc:
    _log("FastMCP server creation failed; MCP server is unavailable.", exc)
    mcp = None

# Active Process Recording Session State
_ACTIVE_SESSION: Optional[Dict[str, Any]] = None
_SESSION_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Core Implementation Functions
# ---------------------------------------------------------------------------

def _get_crop_image(region: Optional[List[int]]) -> Tuple[Image.Image, Optional[List[int]]]:
    """Grab full desktop or crop specified region [x1, y1, x2, y2]."""
    snapshot, union_rect, mapping_info = capture_overlay.grab_full_desktop()
    if region and len(region) == 4:
        x1, y1, x2, y2 = region
        # Normalize bounds
        rx1, rx2 = min(x1, x2), max(x1, x2)
        ry1, ry2 = min(y1, y2), max(y1, y2)
        
        # Shift relative to virtual desktop union_rect if negative origin
        ox, oy = union_rect.x(), union_rect.y()
        crop_box = (
            max(0, rx1 - ox),
            max(0, ry1 - oy),
            min(snapshot.width, rx2 - ox),
            min(snapshot.height, ry2 - oy)
        )
        if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
            snapshot = snapshot.crop(crop_box)
            return snapshot, [rx1, ry1, rx2, ry2]
    
    return snapshot, [union_rect.x(), union_rect.y(), union_rect.x() + union_rect.width(), union_rect.y() + union_rect.height()]


def _rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    r_f, g_f, b_f = r / 255.0, g / 255.0, b / 255.0
    c_max = max(r_f, g_f, b_f)
    c_min = min(r_f, g_f, b_f)
    delta = c_max - c_min

    l = (c_max + c_min) / 2.0
    if delta == 0:
        h = s = 0.0
    else:
        s = delta / (1.0 - abs(2.0 * l - 1.0))
        if c_max == r_f:
            h = ((g_f - b_f) / delta) % 6
        elif c_max == g_f:
            h = (b_f - r_f) / delta + 2
        else:
            h = (r_f - g_f) / delta + 4
        h *= 60.0

    return round(h, 1), round(s * 100, 1), round(l * 100, 1)


def _luminance(r: int, g: int, b: int) -> float:
    a = [v / 255.0 for v in (r, g, b)]
    a = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in a]
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722


def _contrast_ratio(l1: float, l2: float) -> float:
    lum1 = max(l1, l2)
    lum2 = min(l1, l2)
    return round((lum1 + 0.05) / (lum2 + 0.05), 2)


def snippy_take_snip(region: Optional[List[int]] = None) -> Any:
    """Capture screen snip and send the visual screenshot image directly to the AI agent.
    
    Args:
        region: Optional list [x1, y1, x2, y2] specifying bounding box.
    """
    snapshot, actual_rect = _get_crop_image(region)
    try:
        from fastmcp import Image as FastMCPImage
        import io
        buf = io.BytesIO()
        snapshot.save(buf, format="PNG")
        return FastMCPImage(data=buf.getvalue(), format="png")
    except Exception:
        return snapshot



def snippy_ocr_screen(region: Optional[List[int]] = None) -> str:
    """Extract clean text content from the full screen or specified region [x1, y1, x2, y2]."""
    snapshot, _ = _get_crop_image(region)
    parse_res = parser_engine.parse_image(snapshot)
    return parse_res.raw_text if parse_res else ""


def snippy_extract_table(region: Optional[List[int]] = None) -> Dict[str, Any]:
    """Extract geometric tabular data from screen snip as structured JSON and Markdown."""
    snapshot, _ = _get_crop_image(region)
    parse_res = parser_engine.parse_image(snapshot)
    
    return {
        "status": "success",
        "raw_text": parse_res.raw_text if parse_res else "",
        "has_table": bool(parse_res.table) if parse_res else False,
        "rows": parse_res.table if parse_res else [],
        "csv_format": parser_engine.export_csv(parse_res) if parse_res else "",
    }



def snippy_pick_color(x: int, y: int) -> Dict[str, Any]:
    """Sample exact color at pixel coordinates (x, y) on virtual desktop."""
    snapshot, union_rect, _ = capture_overlay.grab_full_desktop()
    
    ox, oy = union_rect.x(), union_rect.y()
    px = x - ox
    py = y - oy
    
    if 0 <= px < snapshot.width and 0 <= py < snapshot.height:
        r, g, b = snapshot.getpixel((px, py))[:3]
        hex_val = f"#{r:02x}{g:02x}{b:02x}".upper()
        h, s, l = _rgb_to_hsl(r, g, b)
        lum = _luminance(r, g, b)
        
        return {
            "coordinates": {"x": x, "y": y},
            "hex": hex_val,
            "rgb": [r, g, b],
            "hsl": {"h_deg": h, "s_pct": s, "l_pct": l},
            "perceived_brightness_pct": round(lum * 100, 1),
            "contrast_ratio": {
                "against_white": _contrast_ratio(lum, 1.0),
                "against_black": _contrast_ratio(lum, 0.0),
            }
        }
        
    return {"error": f"Coordinates ({x}, {y}) out of screen bounds ({union_rect.width()}x{union_rect.height()})"}


def snippy_get_color_palette(region: Optional[List[int]] = None, max_colors: int = 5) -> Dict[str, Any]:
    """Extract dominant color palette from screen or region with distribution percentages."""
    snapshot, actual_rect = _get_crop_image(region)
    
    quantized = snapshot.quantize(colors=max_colors)
    palette = quantized.getpalette()
    colors = quantized.getcolors()
    
    total_pixels = snapshot.width * snapshot.height
    palette_list = []
    
    if colors and palette:
        sorted_colors = sorted(colors, key=lambda c: c[0], reverse=True)
        for count, index in sorted_colors[:max_colors]:
            r = palette[index * 3]
            g = palette[index * 3 + 1]
            b = palette[index * 3 + 2]
            hex_val = f"#{r:02x}{g:02x}{b:02x}".upper()
            pct = round((count / total_pixels) * 100, 2)
            palette_list.append({
                "hex": hex_val,
                "rgb": [r, g, b],
                "percentage": pct,
                "pixel_count": count
            })
            
    return {
        "region": actual_rect,
        "total_pixels": total_pixels,
        "palette": palette_list
    }


def snippy_measure_region(x1: int, y1: int, x2: int, y2: int) -> Dict[str, Any]:
    """Measure pixel dimensions, aspect ratio, center point, and perimeter for screen region [x1, y1, x2, y2]."""
    min_x, max_x = min(x1, x2), max(x1, x2)
    min_y, max_y = min(y1, y2), max(y1, y2)
    
    width = max_x - min_x
    height = max_y - min_y
    perimeter = 2 * (width + height)
    aspect = round(width / max(height, 1), 3)
    center_x = min_x + width / 2.0
    center_y = min_y + height / 2.0
    
    return {
        "bounding_box": {"x1": min_x, "y1": min_y, "x2": max_x, "y2": max_y},
        "dimensions_px": {"width": width, "height": height},
        "aspect_ratio": f"{width}:{height} ({aspect})",
        "center_point": {"x": center_x, "y": center_y},
        "perimeter_px": perimeter,
    }


def snippy_get_monitor_layout() -> Dict[str, Any]:
    """Get virtual desktop monitor details, physical/logical geometries, and scale factors."""
    snapshot, union_rect, mapping_info = capture_overlay.grab_full_desktop()
    monitors_info = []
    
    for item in mapping_info.get("screen_map", []):
        monitors_info.append({
            "name": item.get("name"),
            "logical_rect": {
                "x": item["log_rect"].x(),
                "y": item["log_rect"].y(),
                "w": item["log_rect"].width(),
                "h": item["log_rect"].height(),
            },
            "physical_rect": {
                "x": item["phys_rect"].x(),
                "y": item["phys_rect"].y(),
                "w": item["phys_rect"].width(),
                "h": item["phys_rect"].height(),
            },
            "scale_x": item.get("scale_x", 1.0),
            "scale_y": item.get("scale_y", 1.0),
            "dpr": item.get("dpr", 1.0),
        })
        
    return {
        "virtual_desktop": {
            "x": union_rect.x(),
            "y": union_rect.y(),
            "width": union_rect.width(),
            "height": union_rect.height(),
        },
        "monitor_count": len(monitors_info),
        "monitors": monitors_info,
    }


def snippy_start_process_session(session_name: str) -> Dict[str, Any]:
    """Initialize a new multi-step process recording session.
    
    Creates a dedicated timestamped folder under captures/ and logs screenshots of each step.
    """
    global _ACTIVE_SESSION
    with _SESSION_LOCK:
        clean_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_name.strip().lower())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"process_{clean_name}_{timestamp}"
        target_dir = os.path.abspath(os.path.join("captures", folder_name))
        os.makedirs(target_dir, exist_ok=True)
        
        _ACTIVE_SESSION = {
            "session_name": session_name,
            "folder_name": folder_name,
            "target_dir": target_dir,
            "created_at": datetime.now().isoformat(),
            "step_count": 0,
            "steps": [],
        }
        
        manifest_path = os.path.join(target_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(_ACTIVE_SESSION, f, indent=2)
            
        return {
            "status": "session_started",
            "session_name": session_name,
            "directory": target_dir,
        }


def snippy_record_step(step_name: str, description: str, region: Optional[List[int]] = None) -> Dict[str, Any]:
    """Capture screen/region for the current process step and log screenshot + metadata to folder."""
    global _ACTIVE_SESSION
    with _SESSION_LOCK:
        if not _ACTIVE_SESSION:
            return {"error": "No active process session found. Call snippy_start_process_session first."}
        
        _ACTIVE_SESSION["step_count"] += 1
        step_num = _ACTIVE_SESSION["step_count"]
        clean_step = re.sub(r'[^a-zA-Z0-9_\-]', '_', step_name.strip().lower())
        filename = f"step_{step_num:02d}_{clean_step}.png"
        filepath = os.path.join(_ACTIVE_SESSION["target_dir"], filename)
        
        snapshot, actual_rect = _get_crop_image(region)
        snapshot.save(filepath, "PNG")
        
        # Run OCR to capture context
        parse_res = parser_engine.parse_image(snapshot)
        ocr_text = parse_res.raw_text if parse_res else ""
        
        step_record = {
            "step_number": step_num,
            "step_name": step_name,
            "description": description,
            "image_file": filename,
            "image_path": filepath,
            "region_captured": actual_rect,
            "ocr_text": ocr_text,
            "timestamp": datetime.now().isoformat(),
        }
        
        _ACTIVE_SESSION["steps"].append(step_record)
        
        # Update manifest.json
        manifest_path = os.path.join(_ACTIVE_SESSION["target_dir"], "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(_ACTIVE_SESSION, f, indent=2)
            
        # Update walkthrough.md
        walkthrough_path = os.path.join(_ACTIVE_SESSION["target_dir"], "walkthrough.md")
        with open(walkthrough_path, "w", encoding="utf-8") as f:
            f.write(f"# Process Walkthrough: {_ACTIVE_SESSION['session_name']}\n\n")
            f.write(f"Started at: {_ACTIVE_SESSION['created_at']}\n\n")
            for s in _ACTIVE_SESSION["steps"]:
                f.write(f"## Step {s['step_number']}: {s['step_name']}\n\n")
                f.write(f"**Description**: {s['description']}\n\n")
                f.write(f"![Step {s['step_number']}](./{s['image_file']})\n\n")
                if s['ocr_text']:
                    f.write(f"<details><summary>Extracted Screen Text</summary>\n\n```\n{s['ocr_text']}\n```\n</details>\n\n")
                f.write("---\n\n")

        return {
            "status": "step_recorded",
            "step_number": step_num,
            "image_path": filepath,
            "walkthrough_path": walkthrough_path,
        }


def snippy_finish_process_session() -> Dict[str, Any]:
    """Finalize active process session and return full summary report with image file paths."""
    global _ACTIVE_SESSION
    with _SESSION_LOCK:
        if not _ACTIVE_SESSION:
            return {"error": "No active process session to finish."}
        
        summary = {
            "status": "session_completed",
            "session_name": _ACTIVE_SESSION["session_name"],
            "total_steps": len(_ACTIVE_SESSION["steps"]),
            "directory": _ACTIVE_SESSION["target_dir"],
            "manifest": os.path.join(_ACTIVE_SESSION["target_dir"], "manifest.json"),
            "walkthrough": os.path.join(_ACTIVE_SESSION["target_dir"], "walkthrough.md"),
            "steps": _ACTIVE_SESSION["steps"],
        }
        
        _ACTIVE_SESSION = None
        return summary


# Register tools on FastMCP server if available
if mcp is not None:
    for tool_fn in [
        snippy_take_snip,
        snippy_ocr_screen,
        snippy_extract_table,
        snippy_pick_color,
        snippy_get_color_palette,
        snippy_measure_region,
        snippy_get_monitor_layout,
        snippy_start_process_session,
        snippy_record_step,
        snippy_finish_process_session,
    ]:
        mcp.tool()(tool_fn)


# ---------------------------------------------------------------------------
# FastMCP Server Launchers (SSE / Stdio)
# ---------------------------------------------------------------------------

_SERVER_THREAD = None


def _ensure_stdio_handles() -> None:
    """Windowed PyInstaller apps may have no stdout/stderr for Uvicorn logging."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def start_mcp_sse_server(host: str = "127.0.0.1", port: int = 8000) -> Optional[threading.Thread]:
    """Start FastMCP SSE server in a daemon background thread."""
    global _SERVER_THREAD
    if mcp is None:
        msg = "[Snippy MCP] FastMCP module not installed or failed to import. Server not started."
        print(msg)
        _log(msg)
        return None

    def _run_server():
        try:
            _ensure_stdio_handles()
            msg = f"[Snippy MCP] Starting FastMCP SSE server on http://{host}:{port}/sse ..."
            print(msg)
            _log(msg)
            mcp.run(transport="sse", host=host, port=port)
        except Exception as exc:
            msg = f"[Snippy MCP] Server error: {exc}"
            print(msg)
            _log(msg, exc)

    _SERVER_THREAD = threading.Thread(target=_run_server, daemon=True)
    _SERVER_THREAD.start()
    return _SERVER_THREAD


def run_mcp_stdio():
    """Run FastMCP stdio server for CLI connector mode."""
    if mcp is None:
        raise RuntimeError("FastMCP is not installed. Please run: pip install fastmcp uvicorn")
    _log("[Snippy MCP] Starting FastMCP stdio server.")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        run_mcp_stdio()
    else:
        start_mcp_sse_server()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[Snippy MCP] Shutting down...")
