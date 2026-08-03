"""RapidOCR backend — default, no system binary required."""

from __future__ import annotations

import numpy as np
from PIL import Image

from ocr.base import TextLine


class RapidOcrBackend:
    name = "rapidocr"

    def __init__(self) -> None:
        self._engine = None
        self._init_error: str | None = None
        self._init()

    def _init(self) -> None:
        try:
            from rapidocr import RapidOCR
            self._engine = RapidOCR()
        except Exception as exc:
            self._init_error = str(exc)

    def is_available(self) -> bool:
        return self._engine is not None

    def recognize(self, image: Image.Image) -> tuple[str, list[TextLine]]:
        if not self.is_available():
            raise RuntimeError(f"RapidOCR not available: {self._init_error}")

        img_array = np.array(image.convert("RGB"))
        result = self._engine(img_array, return_word_box=True)

        lines: list[TextLine] = []

        # RapidOCR 3.x returns a result object with .boxes / .txts / .scores
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)

        # Fallback: some versions return raw list-of-tuples
        if boxes is None and result is not None:
            raw = result[0] if isinstance(result, (list, tuple)) and result else []
            boxes = [r[0] for r in raw] if raw else []
            txts = [r[1] for r in raw] if raw else []
            scores = [r[2] if len(r) > 2 else 1.0 for r in raw] if raw else []

        if boxes is None or (hasattr(boxes, '__len__') and len(boxes) == 0):
            return "", []

        items = list(zip(boxes, txts, scores or [1.0] * len(boxes)))
        # Sort top-to-bottom, left-to-right by centre of bbox
        def centre(box):
            pts = box
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return (sum(ys) / len(ys), sum(xs) / len(xs))

        items.sort(key=lambda t: centre(t[0]))

        for box, txt, score in items:
            if not txt:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x = int(min(xs))
            y = int(min(ys))
            w = int(max(xs) - min(xs))
            h = int(max(ys) - min(ys))
            lines.append(TextLine(text=str(txt), bbox=(x, y, w, h), confidence=float(score)))

        raw_text = "\n".join(ln.text for ln in lines)
        return raw_text, lines
