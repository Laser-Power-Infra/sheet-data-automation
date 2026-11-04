from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import gspread

from ..common.config import BASE_DIR
from ..common.errors import ParseError
from ..common.google import column_index, scan_dates, sheet_op
from ..common.pdftext import extract_text, parse_price

LOGGER = logging.getLogger(__name__)

TOP_MARKER = "A. Aluminium"
TOP_END_MARKER = "NOTE:"
INGOT_MARKER = "a. INGOTS/ALUMINIUM HOT METAL."
ROD_MARKER = "b. RODS."
ALLOY_MARKER = "C.ALLOY RODS."
ALLOY_END_MARKER = "For Cable"

DATE_LINE = re.compile(r"^\s*(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s*$")
NUMBER = re.compile(r"[\d,]+")

COLUMNS = {
    "ec": ("C", "D", "E"),
    "ingot": ("O", "P", "Q", "R", "S"),
    "rod": ("AM", "AN", "AO", "AP", "AQ"),
    "alloy": ("AS", "AT", "AV"),
}
TARGET_COLUMNS = tuple(column for group in COLUMNS.values() for column in group)


@dataclass(frozen=True)
class CircularData:
    ec: dict[dt.date, tuple[int, ...]]
    ingots: dict[dt.date, tuple[int, ...]]
    rods: dict[dt.date, tuple[int, ...]]
    alloy_rods: dict[dt.date, tuple[int, ...]]

    @property
    def dates(self) -> list[dt.date]:
        return sorted(self.ec)


def parse_circular_text(text: str) -> CircularData:
    ec = _parse_section(_section(text, TOP_MARKER, TOP_END_MARKER), 3, "top table")
    ingots = _parse_section(
        _section(text, INGOT_MARKER, ROD_MARKER), 5, "a. INGOTS/ALUMINIUM HOT METAL"
    )
    rods = _parse_section(_section(text, ROD_MARKER, ALLOY_MARKER), 5, "b. RODS")
    alloy = _parse_section(
        _section(text, ALLOY_MARKER, ALLOY_END_MARKER), 3, "C.ALLOY RODS"
    )

    _validate_dates(ec, ingots, rods, alloy)
    _validate_averages(ec, ingots, rods, alloy)
    return CircularData(ec=ec, ingots=ingots, rods=rods, alloy_rods=alloy)


def parse_circular_pdf(path: Path) -> CircularData:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ParseError(f"Could not read PDF {path}: {exc}") from exc
    return parse_circular_text(extract_text(data, layout=True))


def build_circular_rows(data: CircularData) -> dict[dt.date, dict[str, int]]:
    dates = data.dates
    if not dates:
        raise ParseError("No dates found in the circular")
    start, end = dates[0], dates[-1]

    groups = {
        "ec": _carry_forward(data.ec, start, end),
        "ingot": _carry_forward(data.ingots, start, end),
        "rod": _carry_forward(data.rods, start, end),
        "alloy": _carry_forward(data.alloy_rods, start, end),
    }

    rows: dict[dt.date, dict[str, int]] = {}
    day = start
    while day <= end:
        row: dict[str, int] = {}
        for group, columns in COLUMNS.items():
            values = groups[group].get(day)
            if values is None:
                continue
            row.update(zip(columns, values, strict=True))
        rows[day] = row
        day += dt.timedelta(days=1)
    return rows


def sync_rows(
    worksheet: gspread.Worksheet,
    rows: dict[dt.date, dict[str, int]],
    *,
    date_column: str = "A",
    apply: bool,
) -> dict[str, int]:
    existing_by_date, _, _ = scan_dates(worksheet, date_column)
    missing: list[dt.date] = []
    targets: list[tuple[dt.date, int, dict[str, int]]] = []
    for day, values in rows.items():
        row_number = existing_by_date.get(day)
        if row_number is None:
            missing.append(day)
            continue
        targets.append((day, row_number, values))

    for day in missing:
        LOGGER.warning("No sheet row for %s; skipped", day.isoformat())

    planned: list[tuple[dt.date, int, dict[str, int], dict[str, object]]] = []
    if targets:
        min_row = min(row for _, row, _ in targets)
        max_row = max(row for _, row, _ in targets)
        matrix = _read_target_rows(worksheet, min_row, max_row)
        for day, row_number, values in targets:
            offset = row_number - min_row
            current = _row_target_values(matrix[offset] if offset < len(matrix) else [])
            changes = {
                column: value
                for column, value in values.items()
                if not _same_number(current.get(column), value)
            }
            if changes:
                planned.append((day, row_number, changes, current))

    if not planned:
        LOGGER.info("No changes needed")
        return {"dates": len(rows), "rows": 0, "cells": 0, "missing": len(missing)}

    cells = sum(len(changes) for _, _, changes, _ in planned)
    LOGGER.info(
        "Planned changes: %s row(s), %s cell(s), %s missing date(s)",
        len(planned),
        cells,
        len(missing),
    )
    for day, row_number, changes, _ in planned:
        LOGGER.info(
            "%s row %s: %s",
            day.isoformat(),
            row_number,
            ", ".join(f"{column}={value}" for column, value in changes.items()),
        )

    if not apply:
        LOGGER.info("DRY_RUN: no cells written (pass --apply to write)")
        return {"dates": len(rows), "rows": len(planned), "cells": cells, "missing": len(missing)}

    backup = {
        f"{column}{row_number}": current.get(column)
        for _, row_number, changes, current in planned
        for column in changes
    }
    backup_path = _write_backup(backup)
    LOGGER.info("Saved cell backup to %s", backup_path)

    updates = [
        {"range": f"{column}{row_number}", "values": [[value]]}
        for _, row_number, changes, _ in planned
        for column, value in changes.items()
    ]
    _write_updates(worksheet, updates)
    LOGGER.info("Wrote %s cell(s) across %s row(s)", cells, len(planned))
    return {"dates": len(rows), "rows": len(planned), "cells": cells, "missing": len(missing)}


@sheet_op
def _read_target_rows(
    worksheet: gspread.Worksheet,
    start_row: int,
    end_row: int,
) -> list[list[object]]:
    return worksheet.get(
        f"C{start_row}:AV{end_row}",
        value_render_option="UNFORMATTED_VALUE",
    )


def _row_target_values(cells: list[object]) -> dict[str, object]:
    base = column_index("C") - 1
    result: dict[str, object] = {}
    for column in TARGET_COLUMNS:
        index = column_index(column) - 1 - base
        result[column] = cells[index] if 0 <= index < len(cells) else None
    return result


@sheet_op
def _write_updates(worksheet: gspread.Worksheet, updates: list[dict[str, object]]) -> None:
    worksheet.batch_update(updates, value_input_option="USER_ENTERED")


def _write_backup(backup: dict[str, object]) -> Path:
    folder = BASE_DIR / "state" / "backups"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"cacmai-import-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.json"
        path.write_text(json.dumps(backup, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Could not write import backup: {exc}") from exc
    return path


def _section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise ParseError(f"Section header not found: {start!r}")
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise ParseError(f"Section end not found: {end!r}")
    return text[start_index + len(start) : end_index]


def _parse_section(
    section: str,
    expected: int,
    label: str,
) -> dict[dt.date, tuple[int, ...]]:
    rows: dict[dt.date, tuple[int, ...]] = {}
    for line in section.splitlines():
        match = DATE_LINE.match(line)
        if not match:
            continue
        day = _parse_date(match.group(1))
        tokens = NUMBER.findall(match.group(2))
        if len(tokens) != expected:
            raise ParseError(
                f"{label}: expected {expected} values on {day.isoformat()}, got {len(tokens)}"
            )
        values = tuple(parse_price(token) for token in tokens)
        previous = rows.get(day)
        if previous is not None and previous != values:
            raise ParseError(f"{label}: conflicting values for {day.isoformat()}")
        rows[day] = values
    if not rows:
        raise ParseError(f"{label}: no data rows found")
    return rows


def _parse_date(value: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError as exc:
        raise ParseError(f"Invalid date in circular: {value!r}") from exc


def _validate_dates(
    ec: dict[dt.date, tuple[int, ...]],
    ingots: dict[dt.date, tuple[int, ...]],
    rods: dict[dt.date, tuple[int, ...]],
    alloy: dict[dt.date, tuple[int, ...]],
) -> None:
    expected = set(ec)
    for label, values in (
        ("a. INGOTS/ALUMINIUM HOT METAL", ingots),
        ("b. RODS", rods),
        ("C.ALLOY RODS", alloy),
    ):
        if set(values) != expected:
            raise ParseError(f"{label}: dates do not match the top table")


def _validate_averages(
    ec: dict[dt.date, tuple[int, ...]],
    ingots: dict[dt.date, tuple[int, ...]],
    rods: dict[dt.date, tuple[int, ...]],
    alloy: dict[dt.date, tuple[int, ...]],
) -> None:
    for day, top in ec.items():
        expected = (ingots[day][-1], rods[day][-1], alloy[day][-1])
        if top != expected:
            raise ParseError(
                f"Top-table values do not match section averages on {day.isoformat()}: "
                f"{top} != {expected}"
            )


def _carry_forward(
    values: dict[dt.date, tuple[int, ...]],
    start: dt.date,
    end: dt.date,
) -> dict[dt.date, tuple[int, ...]]:
    result: dict[dt.date, tuple[int, ...]] = {}
    current: tuple[int, ...] | None = None
    day = start
    while day <= end:
        if day in values:
            current = values[day]
        if current is not None:
            result[day] = current
        day += dt.timedelta(days=1)
    return result


def _same_number(current: object, value: int) -> bool:
    try:
        return int(str(current).replace(",", "").strip()) == value
    except (TypeError, ValueError):
        return False
