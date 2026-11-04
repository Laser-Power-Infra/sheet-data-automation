from __future__ import annotations

import datetime as dt
import functools
import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

import gspread
import requests
from google.oauth2.service_account import Credentials

from .config import AppConfig
from .errors import ConfigError, SheetError
from .retry import retry_call

LOGGER = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_EPOCH = dt.date(1899, 12, 30)
FIRST_DATA_ROW = 5
MAX_BACKFILL_DAYS = 366
MIN_PLAUSIBLE_SERIAL = 40000
MAX_PLAUSIBLE_SERIAL = 100000

@dataclass(frozen=True)
class TargetRow:
    row: int
    existing: bool


def to_serial(value: dt.date) -> int:
    return (value - SHEET_EPOCH).days


def from_serial(value: object) -> dt.date | None:
    try:
        serial = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(serial) or not (
        MIN_PLAUSIBLE_SERIAL <= serial <= MAX_PLAUSIBLE_SERIAL
    ):
        return None
    return SHEET_EPOCH + dt.timedelta(days=int(serial))


def column_index(letter: str) -> int:
    index = 0
    for char in letter.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _api_code(exc: gspread.exceptions.APIError) -> int | None:
    code = getattr(exc, "code", None)
    if not isinstance(code, int) or code <= 0:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def describe_sheet_error(exc: BaseException) -> SheetError | None:
    if isinstance(exc, gspread.exceptions.APIError):
        code = _api_code(exc)
        error = getattr(exc, "error", {})
        detail = error.get("message") if isinstance(error, Mapping) else None
        detail = detail or str(exc)
        if code in (401, 403):
            return SheetError(
                "Google Sheets permission denied. Share the spreadsheet with the "
                f"service account as Editor and check protected ranges. {detail}"
            )
        if code == 404:
            return SheetError(
                "Google Sheets spreadsheet or tab not found; check SPREADSHEET_ID "
                f"and the configured tab/gid. {detail}"
            )
        if code == 429:
            return SheetError(f"Google Sheets rate limit reached after retries. {detail}")
        if code is not None and code >= 500:
            return SheetError(f"Google Sheets is unavailable (HTTP {code}) after retries.")
        return SheetError(f"Google Sheets API error {code or 'unknown'}: {detail}")

    if isinstance(exc, gspread.exceptions.SpreadsheetNotFound):
        return SheetError(
            "Spreadsheet not found; check SPREADSHEET_ID and share it with the service "
            "account as Editor."
        )
    if isinstance(exc, gspread.exceptions.WorksheetNotFound):
        return SheetError("Worksheet/tab not found; check TAB_NAME or the configured gid.")
    if isinstance(exc, requests.exceptions.RequestException):
        return SheetError(f"Could not reach Google Sheets: {exc}")
    return None


def raise_sheet_error(exc: Exception) -> NoReturn:
    mapped = describe_sheet_error(exc)
    if mapped is not None:
        raise mapped from exc
    raise exc


def _call[**P, R](func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    try:
        return retry_call(func, *args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise_sheet_error(exc)


def sheet_op[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Retry transient Google errors and convert the rest to SheetError."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return _call(func, *args, **kwargs)

    return wrapper


@sheet_op
def scan_dates(
    worksheet: gspread.Worksheet,
    column: str = "A",
    *,
    first_row: int = FIRST_DATA_ROW,
) -> tuple[dict[dt.date, int], int | None, dt.date | None]:
    values = worksheet.get(
        f"{column}{first_row}:{column}{worksheet.row_count}",
        value_render_option="UNFORMATTED_VALUE",
    )
    last_row: int | None = None
    last_date: dt.date | None = None
    rows_by_date: dict[dt.date, int] = {}
    for offset, cells in enumerate(values):
        if not cells or cells[0] in (None, ""):
            continue
        parsed = from_serial(cells[0])
        if parsed is None:
            continue
        row = first_row + offset
        last_row = row
        last_date = parsed
        rows_by_date[parsed] = row
    return rows_by_date, last_row, last_date


def choose_target_row(
    today_row: int | None,
    last_row: int | None,
    last_date: dt.date | None,
    today: dt.date,
    *,
    first_row: int = FIRST_DATA_ROW,
) -> TargetRow:
    if today_row is not None:
        return TargetRow(row=today_row, existing=True)
    if last_row is None:
        return TargetRow(row=first_row, existing=False)
    if last_date is not None and today > last_date:
        return TargetRow(row=last_row + 1, existing=False)
    raise ValueError(
        f"Sheet is ahead of {today.isoformat()} (last date {last_date}); refusing to append"
    )


def gap_dates(last_date: dt.date | None, today: dt.date) -> list[dt.date]:
    """Dates strictly between the last sheet date and today (missed runs)."""
    if last_date is None:
        return []
    return [last_date + dt.timedelta(days=n) for n in range(1, (today - last_date).days)]


def backfill_gap_rows(
    worksheet: gspread.Worksheet,
    last_row: int | None,
    last_date: dt.date | None,
    today: dt.date,
    *,
    end_column: str = "AA",
    dry_run: bool = False,
) -> int | None:
    """Carry the previous row into each skipped date so date VLOOKUPs never miss.

    Returns the new last row.
    """
    dates = gap_dates(last_date, today)
    if last_row is None or not dates:
        return last_row
    if len(dates) > MAX_BACKFILL_DAYS:
        raise ValueError(
            f"{len(dates)} missing days exceeds the {MAX_BACKFILL_DAYS}-day safety limit; "
            "refusing to backfill"
        )
    width = column_index(end_column)
    requests_: list[dict[str, Any]] = []
    for offset, missed in enumerate(dates, start=1):
        row_index = last_row - 1 + offset  # 0-based index of the new row
        grid = {"sheetId": worksheet.id, "startColumnIndex": 0, "endColumnIndex": width}
        requests_.append(
            {
                "copyPaste": {
                    "source": {**grid, "startRowIndex": row_index - 1, "endRowIndex": row_index},
                    "destination": {**grid, "startRowIndex": row_index, "endRowIndex": row_index + 1},
                    "pasteType": "PASTE_NORMAL",
                }
            }
        )
        requests_.append(
            {
                "updateCells": {
                    "start": {"sheetId": worksheet.id, "rowIndex": row_index, "columnIndex": 0},
                    "rows": [{"values": [{"userEnteredValue": {"numberValue": to_serial(missed)}}]}],
                    "fields": "userEnteredValue",
                }
            }
        )
    LOGGER.warning(
        "%s: missed run(s) for %s; %s previous row into them",
        worksheet.title,
        ", ".join(d.isoformat() for d in dates),
        "would carry" if dry_run else "carrying",
    )
    if not dry_run:
        _call(worksheet.spreadsheet.batch_update, {"requests": requests_})
    return last_row + len(dates)


def open_worksheet(
    app: AppConfig,
    *,
    tab_name: str | None = None,
    gid: int | None = None,
) -> gspread.Worksheet:
    try:
        credentials = Credentials.from_service_account_info(
            {
                "client_email": app.service_account_email,
                "private_key": app.service_account_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES,
        )
    except Exception as exc:
        raise ConfigError(
            "Invalid Google service account credentials; check "
            "GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_PRIVATE_KEY."
        ) from exc

    client = _call(gspread.authorize, credentials)
    spreadsheet = _call(client.open_by_key, app.spreadsheet_id)
    if gid is not None:
        return _call(spreadsheet.get_worksheet_by_id, gid)
    if tab_name is None:
        raise ValueError("Either tab_name or gid must be provided")
    return _call(spreadsheet.worksheet, tab_name)


def build_cell_updates(
    row: int,
    values: dict[str, object],
) -> list[dict[str, Any]]:
    return [
        {"range": f"{column}{row}", "values": [[value]]} for column, value in sorted(values.items())
    ]


def is_filled(value: object) -> bool:
    return value is not None and str(value).strip() != ""


@sheet_op
def read_columns(
    worksheet: gspread.Worksheet,
    row: int,
    columns: tuple[str, ...],
) -> dict[str, object]:
    if not columns:
        return {}

    ordered = sorted(columns, key=column_index)
    first, last = ordered[0], ordered[-1]
    values = worksheet.get(
        f"{first}{row}:{last}{row}",
        value_render_option="UNFORMATTED_VALUE",
    )
    cells = values[0] if values else []
    base = column_index(first)
    return {
        column: cells[column_index(column) - base]
        if 0 <= column_index(column) - base < len(cells)
        else None
        for column in columns
    }


def missing_columns(
    values: Mapping[str, object],
    columns: tuple[str, ...],
) -> list[str]:
    return [column for column in columns if not is_filled(values.get(column))]
