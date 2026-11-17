"""Registry + entry point used by the upload UI (api/app.py)."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from dataclasses import dataclass

from ..cacmai_conductors.config import load_cacmai_config
from ..common.config import load_app_config
from ..common.errors import ParseError
from ..common.google import open_worksheet, sheet_op
from ..common.pdftext import extract_text
from . import cacmai_circular, ieema_cables_circular, ieema_circular, ieema_mvcc_circular
from .cacmai_circular import sync_rows

MAX_PDF_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Importer:
    label: str
    marker: str  # case-insensitive text every circular of this kind contains
    parse: Callable[[str], object]
    build_rows: Callable[[object], dict]
    columns: tuple[str, ...]
    backup_prefix: str
    tab_name: Callable[[], str]
    date_column: Callable[[], str] = lambda: "A"
    number_format_columns: tuple[str, ...] = ()  # given "0.00" after a write (rows may be unformatted)


IMPORTERS: dict[str, Importer] = {
    "cacmai": Importer(
        label="CACMAI circular",
        marker="BASIC PRICE INDEX CIRCULAR",
        parse=cacmai_circular.parse_circular_text,
        build_rows=cacmai_circular.build_circular_rows,
        columns=cacmai_circular.TARGET_COLUMNS,
        backup_prefix="cacmai-import",
        tab_name=lambda: load_cacmai_config().tab_name,
        date_column=lambda: load_cacmai_config().date_column,
    ),
    "ieema-conductor": Importer(
        label="IEEMA Conductor circular",
        marker="AL Conductor-LME",
        parse=ieema_circular.parse_ieema_text,
        build_rows=ieema_circular.build_ieema_rows,
        columns=ieema_circular.TARGET_COLUMNS,
        backup_prefix="ieema-import",
        tab_name=lambda: "IEEMA CONDUCTOR",
    ),
    "ieema-cables": Importer(
        label="IEEMA Cables circular",
        marker="IEEMA(PVC)CABLE",
        parse=ieema_cables_circular.parse_cables_text,
        build_rows=ieema_cables_circular.build_cables_rows,
        columns=ieema_cables_circular.TARGET_COLUMNS,
        backup_prefix="ieema-cables-import",
        tab_name=lambda: "IEEMA CABLES",
        number_format_columns=("W", "X", "Y", "Z", "AA", "AB", "AC"),
    ),
    "ieema-mvcc": Importer(
        label="IEEMA MVCC circular",
        marker="IEEMA(PVC)/MVCC",
        parse=ieema_mvcc_circular.parse_mvcc_text,
        build_rows=ieema_cables_circular.build_cables_rows,
        columns=ieema_mvcc_circular.TARGET_COLUMNS,
        backup_prefix="ieema-mvcc-import",
        tab_name=lambda: "IEEMA CABLES",
        number_format_columns=("AD",),
    ),
}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).upper()


def validate_pdf(kind: str, data: bytes) -> str:
    """Return the PDF text, or raise ParseError with a user-facing message."""
    importer = IMPORTERS[kind]
    if not data.startswith(b"%PDF"):
        raise ParseError("That file is not a PDF.")
    if len(data) > MAX_PDF_BYTES:
        raise ParseError(f"PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    text = extract_text(data, layout=True)
    if not text.strip():
        raise ParseError("No text could be read from this PDF (scanned image?).")
    squashed = _squash(text)
    if _squash(importer.marker) not in squashed:
        for other_kind, other in IMPORTERS.items():
            if other_kind != kind and _squash(other.marker) in squashed:
                raise ParseError(
                    f"This looks like the {other.label}, not the {importer.label}. "
                    "Upload it in the matching section."
                )
        raise ParseError(f"This PDF does not look like a {importer.label}.")
    return text


@sheet_op
def _apply_number_format(worksheet, columns: tuple[str, ...], first_row: int, last_row: int) -> None:
    for column in columns:
        worksheet.format(
            f"{column}{first_row}:{column}{last_row}",
            {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
        )


MAX_VALUE = 5_000_000  # Rs/MT prices are ~3-4 lakh; anything beyond is a mis-parse
DATE_WINDOW = (dt.timedelta(days=400), dt.timedelta(days=45))  # (past, future) vs today


def check_rows(rows: dict, today: dt.date | None = None) -> None:
    """Sanity-check parsed rows before the sheet is touched; raises ParseError."""
    today = today or dt.date.today()
    if not rows:
        raise ParseError("No dates could be read from this PDF.")
    first, last = min(rows), max(rows)
    if first < today - DATE_WINDOW[0] or last > today + DATE_WINDOW[1]:
        raise ParseError(
            f"Dates {first.isoformat()} to {last.isoformat()} look wrong for today ({today.isoformat()}). "
            "Check that this is the right circular."
        )
    for day, cells in rows.items():
        for column, value in cells.items():
            if not isinstance(value, int | float) or not 0 < value < MAX_VALUE:
                raise ParseError(f"Unreasonable value {value!r} for column {column} on {day.isoformat()}.")


def run_import(kind: str, data: bytes, *, apply: bool) -> dict[str, object]:
    importer = IMPORTERS[kind]
    parsed = importer.parse(validate_pdf(kind, data))
    rows = importer.build_rows(parsed)
    check_rows(rows)
    days = sorted(rows)
    worksheet = open_worksheet(load_app_config(), tab_name=importer.tab_name())
    summary = sync_rows(
        worksheet,
        rows,
        date_column=importer.date_column(),
        apply=apply,
        columns=importer.columns,
        backup_prefix=importer.backup_prefix,
    )
    preview = summary["preview"]
    if apply and preview and importer.number_format_columns:
        written = [item["row"] for item in preview]
        _apply_number_format(worksheet, importer.number_format_columns, min(written), max(written))
    return {
        **summary,
        "kind": kind,
        "label": importer.label,
        "tab": importer.tab_name(),
        "applied": apply,
        "first_date": days[0].isoformat(),
        "last_date": days[-1].isoformat(),
    }
