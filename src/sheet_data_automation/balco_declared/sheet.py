from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from typing import Any

import gspread

from ..common.config import AppConfig
from ..common.google import column_index, is_filled, open_worksheet, read_columns, sheet_op
from .config import BalcoDeclaredConfig

LOGGER = logging.getLogger(__name__)

BALCO_FILL_COLUMNS = (
    "B",
    "D",
    "F",
    "G",
    "H",
    "I",
    "J",
    "K",
    "L",
    "M",
    "S",
    "T",
    "U",
    "Y",
    "Z",
    "AA",
)
FILL_START_COLUMN = "A"
FILL_END_COLUMN = "AA"


def build_fill_ranges(
    inserted_columns: tuple[str, ...],
    *,
    start_column: str = FILL_START_COLUMN,
    end_column: str = FILL_END_COLUMN,
) -> list[tuple[int, int]]:
    start = column_index(start_column) - 1
    end = column_index(end_column) - 1
    excluded = {column_index(column) - 1 for column in inserted_columns}

    ranges: list[tuple[int, int]] = []
    run_start: int | None = None
    for index in range(start, end + 1):
        if index in excluded:
            if run_start is not None:
                ranges.append((run_start, index))
                run_start = None
            continue
        if run_start is None:
            run_start = index
    if run_start is not None:
        ranges.append((run_start, end + 1))
    return ranges


def row_needs_fill(values: Mapping[str, object], columns: tuple[str, ...]) -> bool:
    return any(not is_filled(values.get(column)) for column in columns)


class BalcoDeclaredSheet:
    def __init__(self, app: AppConfig, config: BalcoDeclaredConfig) -> None:
        self.app = app
        self.config = config
        self._worksheet: gspread.Worksheet | None = None

    @property
    def worksheet(self) -> gspread.Worksheet:
        if self._worksheet is None:
            self._worksheet = open_worksheet(self.app, gid=self.config.gid)
        return self._worksheet

    @sheet_op
    def read_link(self, cell: str | None = None) -> str:
        cell = cell or self.config.link_cell
        value = self.worksheet.acell(cell).value
        if not value or not value.strip():
            raise ValueError(f"{cell} is empty")
        return value.strip()

    @sheet_op
    def read_rate(self, row: int) -> Any:
        return self.worksheet.acell(f"{self.config.rate_column}{row}").value

    def read_values(self, row: int, columns: tuple[str, ...]) -> dict[str, object]:
        return read_columns(self.worksheet, row, columns)

    def write_date(self, row: int, run_date: dt.date) -> None:
        self._write(row, self.config.date_column, run_date.isoformat())

    def write_rate(self, row: int, rate: float) -> None:
        self._write(row, self.config.rate_column, rate)

    @sheet_op
    def write_values(self, row: int, values: dict[str, object]) -> None:
        if not values:
            return
        updates = [
            {"range": f"{column}{row}", "values": [[value]]}
            for column, value in sorted(values.items())
        ]
        self.worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        LOGGER.info(
            "Wrote row %s: %s",
            row,
            ", ".join(f"{column}={value}" for column, value in sorted(values.items())),
        )

    def needs_fill(self, row: int, columns: tuple[str, ...] = BALCO_FILL_COLUMNS) -> bool:
        return row_needs_fill(self.read_values(row, columns), columns)

    @sheet_op
    def fill_other_columns(
        self,
        row: int,
        inserted_columns: tuple[str, ...],
        *,
        fill_columns: tuple[str, ...] = BALCO_FILL_COLUMNS,
    ) -> bool:
        source_row = row - 1
        if source_row < 1:
            LOGGER.warning("No previous row for row %s; skipping fill-down", row)
            return False
        if not self.needs_fill(row, fill_columns):
            LOGGER.info("Row %s already has the other columns; skipping fill-down", row)
            return False
        if row_needs_fill(self.read_values(source_row, fill_columns), fill_columns):
            LOGGER.warning(
                "Row %s is missing fill columns; skipping fill-down to row %s",
                source_row,
                row,
            )
            return False

        ranges = build_fill_ranges(inserted_columns)
        requests = [
            {
                "copyPaste": {
                    "source": {
                        "sheetId": self.worksheet.id,
                        "startRowIndex": source_row - 1,
                        "endRowIndex": source_row,
                        "startColumnIndex": start,
                        "endColumnIndex": end,
                    },
                    "destination": {
                        "sheetId": self.worksheet.id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": start,
                        "endColumnIndex": end,
                    },
                    "pasteType": "PASTE_NORMAL",
                    "pasteOrientation": "NORMAL",
                }
            }
            for start, end in ranges
        ]
        self.worksheet.spreadsheet.batch_update({"requests": requests})

        after = self.read_values(row, fill_columns)
        missing = [column for column in fill_columns if not is_filled(after.get(column))]
        if missing:
            raise RuntimeError(f"Fill-down left columns empty on row {row}: {', '.join(missing)}")

        LOGGER.info(
            "Copied non-inserted columns from row %s to row %s",
            source_row,
            row,
        )
        return True

    @sheet_op
    def _write(self, row: int, column: str, value: object) -> None:
        self.worksheet.batch_update(
            [{"range": f"{column}{row}", "values": [[value]]}],
            value_input_option="USER_ENTERED",
        )
        LOGGER.info("Wrote %s to %s%s", value, column, row)
