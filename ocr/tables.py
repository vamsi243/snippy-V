"""Table reconstruction from OCR text lines.

Tier 1: geometric clustering (default, zero extra deps).
Tier 2: RapidTable (optional, requires rapid_table package).
"""

from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ocr.base import TextLine


# ---------------------------------------------------------------------------
# Tier 1 — Geometric reconstruction
# ---------------------------------------------------------------------------

def reconstruct_geometric(lines: list["TextLine"]) -> list[list[str]]:
    """Convert spatially-located TextLines into a 2-D table (rows × cols).

    Falls back to single-column rows if no consistent column structure exists.
    """
    if not lines:
        return []

    # --- compute median line height for row-gap threshold ---
    heights = [ln.bbox[3] for ln in lines if ln.bbox[3] > 0]
    if not heights:
        return [[ln.text] for ln in lines]
    med_h = statistics.median(heights)
    row_gap = max(med_h * 0.6, 4)

    # --- cluster into rows by centre-y ---
    def cy(ln: "TextLine") -> float:
        return ln.bbox[1] + ln.bbox[3] / 2

    sorted_lines = sorted(lines, key=cy)
    rows: list[list["TextLine"]] = []
    current_row: list["TextLine"] = [sorted_lines[0]]

    for ln in sorted_lines[1:]:
        last_cy = cy(current_row[-1])
        if abs(cy(ln) - last_cy) <= row_gap:
            current_row.append(ln)
        else:
            rows.append(sorted(current_row, key=lambda l: l.bbox[0]))
            current_row = [ln]
    rows.append(sorted(current_row, key=lambda l: l.bbox[0]))

    # --- collect x-start positions to infer columns ---
    all_x = [ln.bbox[0] for ln in lines]
    col_boundaries = _cluster_column_starts(all_x, gap_factor=0.8 * med_h)

    if len(col_boundaries) <= 1:
        # No clear column structure → single-column
        return [[" ".join(ln.text for ln in row)] for row in rows]

    # --- assign each fragment to the nearest column ---
    n_cols = len(col_boundaries)
    table: list[list[str]] = []
    for row in rows:
        cells: list[str] = [""] * n_cols
        for ln in row:
            col_idx = _nearest_col(ln.bbox[0], col_boundaries)
            if cells[col_idx]:
                cells[col_idx] += " " + ln.text
            else:
                cells[col_idx] = ln.text
        table.append(cells)

    return table


def _cluster_column_starts(x_positions: list[float], gap_factor: float) -> list[float]:
    """Group x-coordinates into column centres using a simple gap-based pass."""
    if not x_positions:
        return []
    sorted_x = sorted(set(x_positions))
    clusters: list[list[float]] = [[sorted_x[0]]]
    for x in sorted_x[1:]:
        if x - clusters[-1][-1] < gap_factor:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [statistics.mean(c) for c in clusters]


def _nearest_col(x: float, boundaries: list[float]) -> int:
    return min(range(len(boundaries)), key=lambda i: abs(boundaries[i] - x))


# ---------------------------------------------------------------------------
# Tier 2 — RapidTable (optional)
# ---------------------------------------------------------------------------

class RapidTableExtractor:
    """Wraps rapid_table; only instantiated when ENABLE_RAPID_TABLE is True."""

    def __init__(self) -> None:
        from rapid_table import RapidTable, RapidTableInput, ModelType
        self._table = RapidTable(RapidTableInput(model_type=ModelType.SLANETPLUS))

    def extract(self, image_ndarray) -> list[list[str]]:
        import pandas as pd
        out = self._table(image_ndarray)
        if not out or not getattr(out, "pred_html", None):
            return []
        try:
            dfs = pd.read_html(out.pred_html)
            if dfs:
                df = dfs[0]
                return [list(map(str, row)) for row in df.values.tolist()]
        except Exception:
            pass
        return []
