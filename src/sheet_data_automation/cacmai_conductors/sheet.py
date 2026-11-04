from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping
from typing import Any

import gspread

from ..common.config import AppConfig
from ..common.google import (
    TargetRow,
    backfill_gap_rows,
    choose_target_row,
    missing_columns,
    open_worksheet,
    read_columns,
    scan_dates,
    sheet_op,
)
from .config import CacmaiConfig
from .formulas import fill_down_formulas, has_complete_formulas

LOGGER = logging.getLogger(__name__)


class PriceSheet:
    def __init__(self, app: AppConfig, config: CacmaiConfig) -> None:
        self.app = app
        self.config = config
        self._worksheet: gspread.Worksheet | None = None

    @property
    def worksheet(self) -> gspread.Worksheet:
        if self._worksheet is None:
            self._worksheet = open_worksheet(self.app, tab_name=self.config.tab_name)
        return self._worksheet

    @sheet_op
    def read_link(self, cell: str) -> str:
        value = self.worksheet.acell(cell).value
        if not value or not value.strip():
            raise ValueError(f"{cell} is empty")
        return value.strip()

    def find_target_row(self, today: dt.date, *, dry_run: bool = False) -> TargetRow:
        rows_by_date, last_row, last_date = scan_dates(self.worksheet, self.config.date_column)
        today_row = rows_by_date.get(today)
        if today_row is None and last_date is not None and last_date < today:
            last_row = backfill_gap_rows(self.worksheet, last_row, last_date, today, dry_run=dry_run)
            last_date = max(last_date, today - dt.timedelta(days=1))
        target = choose_target_row(today_row, last_row, last_date, today)
        LOGGER.info(
            "Last sheet date: %s (row %s) -> target row %s%s",
            last_date.isoformat() if last_date else None,
            last_row,
            target.row,
            " (updating existing row)" if target.existing else "",
        )
        return target

    @sheet_op
    def write_row(
        self,
        target: TargetRow,
        run_date: dt.date,
        values: Mapping[str, object],
    ) -> None:
        updates = build_row_updates(target.row, run_date, values)
        self.worksheet.batch_update(updates, value_input_option="USER_ENTERED")
        written = ", ".join(
            f"{column}{target.row}={value}" for column, value in sorted(values.items())
        )
        LOGGER.info(
            "Wrote %s to %s%s; %s",
            run_date.isoformat(),
            self.config.date_column,
            target.row,
            written,
        )

    @sheet_op
    def write_date(self, row: int, run_date: dt.date) -> None:
        self.worksheet.batch_update(
            [{"range": f"{self.config.date_column}{row}", "values": [[run_date.isoformat()]]}],
            value_input_option="USER_ENTERED",
        )
        LOGGER.info("Wrote date %s to %s%s", run_date.isoformat(), self.config.date_column, row)

    def fill_down_formulas(self, target_row: int) -> dict[str, str]:
        return fill_down_formulas(self.worksheet, target_row)

    def missing_values(self, row: int, columns: tuple[str, ...]) -> list[str]:
        return missing_columns(read_columns(self.worksheet, row, columns), columns)

    def read_values(self, row: int, columns: tuple[str, ...]) -> dict[str, object]:
        return read_columns(self.worksheet, row, columns)

    def formulas_complete(self, row: int) -> bool:
        return has_complete_formulas(self.worksheet, row)


def build_row_updates(
    row: int,
    run_date: dt.date,
    values: Mapping[str, object],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = [{"range": f"A{row}", "values": [[run_date.isoformat()]]}]
    updates.extend(
        {"range": f"{column}{row}", "values": [[value]]} for column, value in sorted(values.items())
    )
    return updates
