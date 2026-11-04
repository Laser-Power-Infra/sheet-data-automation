from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping

import gspread

from ..common.config import AppConfig
from ..common.google import (
    column_index,
    is_filled,
    open_worksheet,
    read_columns,
    sheet_op,
)
from .config import DragSheetConfig

LOGGER = logging.getLogger(__name__)


def column_letters(start: str, end: str) -> tuple[str, ...]:
    start_index = column_index(start)
    end_index = column_index(end)
    return tuple(_column_letter(index) for index in range(start_index, end_index + 1))


def _column_letter(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def build_contiguous_ranges(columns: tuple[str, ...]) -> list[tuple[int, int]]:
    indices = sorted({column_index(column) - 1 for column in columns})
    if not indices:
        return []
    ranges: list[tuple[int, int]] = []
    run_start = indices[0]
    previous = indices[0]
    for index in indices[1:]:
        if index == previous + 1:
            previous = index
            continue
        ranges.append((run_start, previous + 1))
        run_start = index
        previous = index
    ranges.append((run_start, previous + 1))
    return ranges


def select_dynamic_columns(
    values: Mapping[str, object],
    exclude_columns: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        column
        for column, value in values.items()
        if column not in exclude_columns and is_filled(value)
    )


def filter_missing_columns(
    columns: tuple[str, ...],
    target_values: Mapping[str, object],
) -> tuple[str, ...]:
    return tuple(column for column in columns if not is_filled(target_values.get(column)))


def missing_dates(last_date: dt.date, today: dt.date) -> list[dt.date]:
    dates: list[dt.date] = []
    current = last_date + dt.timedelta(days=1)
    while current <= today:
        dates.append(current)
        current += dt.timedelta(days=1)
    return dates


class DragSheet:
    def __init__(self, app: AppConfig, config: DragSheetConfig) -> None:
        self.app = app
        self.config = config
        self._worksheet: gspread.Worksheet | None = None

    @property
    def worksheet(self) -> gspread.Worksheet:
        if self._worksheet is None:
            self._worksheet = open_worksheet(self.app, gid=self.config.gid)
        return self._worksheet

    def read_values(self, row: int, columns: tuple[str, ...]) -> dict[str, object]:
        return read_columns(self.worksheet, row, columns)

    @sheet_op
    def formula_values(self, row: int) -> dict[str, str]:
        columns = column_letters("A", self.config.fill_end_column)
        values = self.worksheet.get(
            f"A{row}:{self.config.fill_end_column}{row}",
            value_render_option="FORMULA",
        )
        cells = values[0] if values else []
        return {
            column: str(cells[index]) if index < len(cells) else ""
            for index, column in enumerate(columns)
        }

    @sheet_op
    def append_date(self, row: int, value: dt.date) -> None:
        self.worksheet.batch_update(
            [{"range": f"A{row}", "values": [[value.isoformat()]]}],
            value_input_option="USER_ENTERED",
        )
        LOGGER.info("Wrote date %s to A%s", value.isoformat(), row)

    @sheet_op
    def source_columns(self, source_row: int) -> tuple[str, ...]:
        if self.config.columns is not None:
            return self.config.columns

        columns = column_letters("A", self.config.fill_end_column)
        values = self.worksheet.get(
            f"A{source_row}:{self.config.fill_end_column}{source_row}",
            value_render_option="UNFORMATTED_VALUE",
        )
        cells = values[0] if values else []
        mapped = {
            column: cells[index] if index < len(cells) else None
            for index, column in enumerate(columns)
        }
        return select_dynamic_columns(mapped, self.config.exclude_columns)

    def columns_to_fill(self, source_row: int, target_row: int) -> tuple[str, ...]:
        columns = self.source_columns(source_row)
        if not columns:
            return ()
        target_values = self.read_values(target_row, columns)
        target_formulas = self.formula_values(target_row)
        return tuple(
            column
            for column in columns
            if not is_filled(target_values.get(column))
            and not target_formulas.get(column, "").startswith("=")
        )

    @sheet_op
    def copy_columns(
        self,
        source_row: int,
        target_row: int,
        columns: tuple[str, ...],
    ) -> None:
        ranges = build_contiguous_ranges(columns)
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
                        "startRowIndex": target_row - 1,
                        "endRowIndex": target_row,
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
        LOGGER.info(
            "Copied columns %s from row %s to row %s",
            ", ".join(columns),
            source_row,
            target_row,
        )

        after = self.read_values(target_row, columns)
        after_formulas = self.formula_values(target_row)
        blank = [
            column
            for column in columns
            if not is_filled(after.get(column))
            and not after_formulas.get(column, "").startswith("=")
        ]
        if blank:
            LOGGER.warning(
                "Copied but currently blank on row %s (linked data may be missing): %s",
                target_row,
                ", ".join(blank),
            )

    def check_spill_columns(self, row: int) -> None:
        if not self.config.spill_columns:
            return
        values = self.read_values(row, self.config.spill_columns)
        blank = [
            column for column in self.config.spill_columns if not is_filled(values.get(column))
        ]
        if blank:
            LOGGER.warning(
                "Spill column(s) still blank on row %s: %s",
                row,
                ", ".join(blank),
            )
