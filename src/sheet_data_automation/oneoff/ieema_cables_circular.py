from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from ..common.errors import ParseError
from ..common.pdftext import extract_text

# (line regex, sheet column). The circular has one monthly price per item.
CABLE_ITEMS: tuple[tuple[str, str], ...] = (
    (r"LME Average Settlement", "D"),
    (r"Price of copper wire rod", "F"),
    (r"copper wire rod 19\.6 mm", "H"),
    (r"Price of Pig Lead", "J"),
    (r"^\s*PVC\s+Rs\.", "K"),
    (r"^\s*HR PVC\s+Rs\.", "L"),
    (r"For LV Cable", "M"),
    (r"For MV Cable", "AB"),
    (r"For EHV Cable", "W"),
    (r"Polythelene PE ST7", "O"),
    (r"\(LSZH\)", "AC"),
    (r"Round 1\.40 mm", "P"),
    (r"Round 1\.60 mm", "Q"),
    (r"Flat 4 mm x 0\.8 mm", "R"),
    (r"Round 2\.00 mm", "X"),
    (r"Round 2\.50 mm", "Y"),
    (r"Round 3\.15 mm", "Z"),
    (r"Round 4\.00 mm", "AA"),
    (r"25 X 0\.5 mm", "S"),
    (r"32 X 0\.8 mm", "T"),
)
TARGET_COLUMNS = tuple(column for _, column in CABLE_ITEMS)

PRICE = re.compile(r"Rs\.\s*([\d,]+)\s*/\s*MT")
MONTH = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{4})"
)


@dataclass(frozen=True)
class CablesData:
    month_start: dt.date
    prices: dict[str, int]


def parse_cables_text(text: str) -> CablesData:
    month = MONTH.search(text)
    if not month:
        raise ParseError("Month not found in the cables circular")
    month_start = dt.datetime.strptime(f"{month.group(1)} {month.group(2)}", "%B %Y").date()

    prices: dict[str, int] = {}
    for line in text.splitlines():
        price = PRICE.search(line)
        if not price:
            continue
        for pattern, column in CABLE_ITEMS:
            if re.search(pattern, line):
                if column in prices:
                    raise ParseError(f"Duplicate price for column {column}: {line.strip()!r}")
                prices[column] = int(price.group(1).replace(",", ""))
                break
    missing = [column for column in TARGET_COLUMNS if column not in prices]
    if missing:
        raise ParseError(f"Cables circular: no price found for column(s) {', '.join(missing)}")
    return CablesData(month_start=month_start, prices=prices)


def parse_cables_pdf(path: Path) -> CablesData:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"Could not read PDF {path}: {exc}") from exc
    return parse_cables_text(extract_text(data, layout=True))


def build_cables_rows(data: CablesData) -> dict[dt.date, dict[str, int]]:
    days = calendar.monthrange(data.month_start.year, data.month_start.month)[1]
    return {data.month_start.replace(day=day): dict(data.prices) for day in range(1, days + 1)}
