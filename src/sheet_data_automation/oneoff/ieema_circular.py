from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from ..common.errors import ParseError
from ..common.pdftext import extract_text
from .cacmai_circular import _carry_forward

DAILY_COLUMNS = ("E", "F", "C")  # USD price, USD premium, Rs/MT incl. premium + duty
AVERAGE_COLUMN = "G"
STEEL_COLUMNS = ("H", "I", "J", "K", "L")
TARGET_COLUMNS = ("C", "E", "F", "G", *STEEL_COLUMNS)

DAILY_LINE = re.compile(r"^\s*(\d{2}-[A-Za-z]{3}-\d{2})\s+\$([\d,.]+)\s+\$([\d,.]+)\s+([\d,]+)")
AVERAGE_LINE = re.compile(r"^\s*Average\s+\$([\d,.]+)\s+\$([\d,.]+)\s+([\d,]+)")
STEEL_LINE = re.compile(r"Rs\.\D*?([\d,]{4,})\s*/-MT")
STEEL_MARKER = "HIGH TENSILE GALVANISED STEEL WIRE"


@dataclass(frozen=True)
class IeemaData:
    daily: dict[dt.date, tuple[float, float, int]]
    average_inr: int
    steel: tuple[int, ...]

    @property
    def dates(self) -> list[dt.date]:
        return sorted(self.daily)


def _num(raw: str) -> float:
    return float(raw.replace(",", ""))


def parse_ieema_text(text: str) -> IeemaData:
    daily: dict[dt.date, tuple[float, float, int]] = {}
    average: int | None = None
    for line in text.splitlines():
        match = DAILY_LINE.match(line)
        if match:
            try:
                day = dt.datetime.strptime(match.group(1), "%d-%b-%y").date()
            except ValueError as exc:
                raise ParseError(f"Invalid date in circular: {match.group(1)!r}") from exc
            daily[day] = (_num(match.group(2)), _num(match.group(3)), int(_num(match.group(4))))
            continue
        match = AVERAGE_LINE.match(line)
        if match:
            average = int(_num(match.group(3)))
    if not daily:
        raise ParseError("No daily price rows found in the circular")
    if average is None:
        raise ParseError("Average row not found in the circular")

    marker = text.find(STEEL_MARKER)
    if marker < 0:
        raise ParseError(f"Section header not found: {STEEL_MARKER!r}")
    steel = tuple(int(_num(m.group(1))) for m in STEEL_LINE.finditer(text[marker:]))
    if len(steel) != len(STEEL_COLUMNS):
        raise ParseError(f"Expected {len(STEEL_COLUMNS)} steel wire prices, got {len(steel)}")
    return IeemaData(daily=daily, average_inr=average, steel=steel)


def parse_ieema_pdf(path: Path) -> IeemaData:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"Could not read PDF {path}: {exc}") from exc
    return parse_ieema_text(extract_text(data, layout=True))


def build_ieema_rows(data: IeemaData) -> dict[dt.date, dict[str, float]]:
    start, end = data.dates[0], data.dates[-1]
    daily = _carry_forward(data.daily, start, end)  # type: ignore[arg-type]
    fixed = {AVERAGE_COLUMN: data.average_inr, **dict(zip(STEEL_COLUMNS, data.steel, strict=True))}
    return {
        day: {**dict(zip(DAILY_COLUMNS, values, strict=True)), **fixed}
        for day, values in daily.items()
    }
