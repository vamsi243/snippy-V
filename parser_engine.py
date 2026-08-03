"""Orchestrates OCR → table reconstruction → exports → clipboard → Brave search."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

from ocr.base import ParseResult

if TYPE_CHECKING:
    from PIL import Image


# ---------------------------------------------------------------------------
# Core parse
# ---------------------------------------------------------------------------

def parse_image(pil_image: "Image.Image") -> ParseResult:
    """Run OCR + table reconstruction on a PIL crop. Returns ParseResult."""
    import config
    from ocr.tables import reconstruct_geometric

    backend = config.get_backend()
    raw_text, lines = backend.recognize(pil_image)

    table: list[list[str]] = []
    strategy = "none"

    if lines:
        strategy_cfg = config.TABLE_STRATEGY

        if strategy_cfg in ("geometric", "auto"):
            table = reconstruct_geometric(lines)
            strategy = "geometric"

        # Tier 2: try RapidTable if enabled and geometric looks degenerate
        if config.ENABLE_RAPID_TABLE and (
            strategy_cfg == "rapid_table"
            or (strategy_cfg == "auto" and _is_degenerate(table))
        ):
            try:
                import numpy as np
                from ocr.tables import RapidTableExtractor
                extractor = RapidTableExtractor()
                arr = np.array(pil_image.convert("RGB"))
                rt_table = extractor.extract(arr)
                if rt_table:
                    table = rt_table
                    strategy = "rapid_table"
            except Exception as exc:
                print(f"[parser] RapidTable failed, keeping geometric: {exc}")

    return ParseResult(
        raw_text=raw_text,
        lines=lines,
        table=table,
        backend=backend.name,
        table_strategy=strategy,
    )


def _is_degenerate(table: list[list[str]]) -> bool:
    """True if the geometric table has ≤1 column or very low cell fill."""
    if not table:
        return True
    n_cols = max(len(row) for row in table) if table else 0
    if n_cols <= 1:
        return True
    total = sum(len(row) for row in table)
    filled = sum(1 for row in table for cell in row if cell.strip())
    fill_rate = filled / total if total else 0
    return fill_rate < 0.3


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def export_csv(table: list[list[str]], path: str | Path) -> None:
    """Write a 2-D table to a CSV file using Python's built-in csv module (UTF-8-SIG for Excel)."""
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerows(table)


def export_pdf(result: ParseResult, path: str | Path) -> None:
    """Export OCR text + table to a PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                  fontSize=14, spaceAfter=10)
    story.append(Paragraph("Snippy — Captured Text", title_style))
    story.append(Spacer(1, 0.3 * cm))

    # Raw text block
    body_style = styles["BodyText"]
    body_style.wordWrap = "LTR"
    for line in result.raw_text.split("\n"):
        if line.strip():
            story.append(Paragraph(line.strip(), body_style))
    story.append(Spacer(1, 0.5 * cm))

    # Table (if any)
    if result.table:
        tbl_data = result.table
        t = Table(tbl_data, repeatRows=0)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c5cff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f5f8")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccccdd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    doc.build(story)


# ---------------------------------------------------------------------------
# Brave / web search
# ---------------------------------------------------------------------------

def search_brave(text: str, max_chars: int = 2000) -> None:
    """Send text as a Brave search query (falls back to default browser)."""
    import config
    query = text[:max_chars].strip()
    if not query:
        return
    url = "https://search.brave.com/search?q=" + urllib.parse.quote_plus(query)
    config.open_brave(url)
