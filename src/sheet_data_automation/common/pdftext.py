from __future__ import annotations

import io

from pypdf import PdfReader

from .errors import ParseError


def extract_text(data: bytes, *, layout: bool = False) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ParseError(f"Could not read PDF: {exc}") from exc

    pages: list[str] = []
    for page in reader.pages:
        if layout:
            pages.append(page.extract_text(extraction_mode="layout") or "")
        else:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def parse_price(raw: str) -> int:
    try:
        value = int(raw.replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ParseError(f"Invalid price: {raw!r}") from exc
    if value <= 0:
        raise ParseError(f"Invalid price: {value}")
    return value
