"""Optional Tesseract OCR backend (fallback only)."""

from __future__ import annotations

from PIL import Image

from ocr.base import TextLine


class TesseractBackend:
    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract
            import config
            if config.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def recognize(self, image: Image.Image) -> tuple[str, list[TextLine]]:
        import pytesseract
        import config
        if config.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        lines: list[TextLine] = []
        current_line: int | None = None
        line_words: list[tuple[str, list[int], float]] = []

        def flush_line():
            if not line_words:
                return
            texts = [w[0] for w in line_words]
            xs = [w[1][0] for w in line_words]
            ys = [w[1][1] for w in line_words]
            ws = [w[1][2] for w in line_words]
            hs = [w[1][3] for w in line_words]
            x = min(xs)
            y = min(ys)
            w = max(x2 + w2 for x2, w2 in zip(xs, ws)) - x
            h = max(y2 + h2 for y2, h2 in zip(ys, hs)) - y
            conf = sum(w[2] for w in line_words) / len(line_words)
            lines.append(TextLine(text=" ".join(texts), bbox=(x, y, w, h), confidence=conf / 100.0))

        n = len(data["text"])
        for i in range(n):
            word = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not word or conf < 0:
                continue
            line_num = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            if line_num != current_line:
                flush_line()
                line_words = []
                current_line = line_num
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            line_words.append((word, [x, y, w, h], conf))

        flush_line()
        raw_text = "\n".join(ln.text for ln in lines)
        return raw_text, lines
