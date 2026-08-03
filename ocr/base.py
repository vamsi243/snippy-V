"""OCR backend protocol and shared data structures."""

from dataclasses import dataclass, field
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class TextLine:
    text: str
    bbox: tuple[int, int, int, int]  # x, y, w, h in crop pixels
    confidence: float


@dataclass
class ParseResult:
    raw_text: str
    lines: list[TextLine] = field(default_factory=list)
    table: list[list[str]] = field(default_factory=list)  # rows × cols
    backend: str = ""
    table_strategy: str = ""  # "geometric" | "rapid_table" | "none"


class OCRBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def recognize(self, image: "Image.Image") -> tuple[str, list[TextLine]]: ...
