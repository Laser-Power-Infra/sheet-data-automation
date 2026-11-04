from __future__ import annotations

import datetime as dt
import logging

from ..common.config import AppConfig, load_app_config
from ..common.google import MAX_BACKFILL_DAYS, scan_dates
from ..common.result import RunResult
from .config import SHEETS, DragSheetConfig
from .sheet import DragSheet, missing_dates

LOGGER = logging.getLogger("sheet_data_automation.drag_sheets")

WARN_BACKFILL_DAYS = 31


def process_sheet(app: AppConfig, config: DragSheetConfig, *, dry_run: bool) -> str | None:
    sheet = DragSheet(app, config)
    rows_by_date, last_row, last_date = scan_dates(
        sheet.worksheet, "A", first_row=config.first_data_row
    )
    LOGGER.info(
        "%s: last date %s (row %s)",
        config.name,
        last_date.isoformat() if last_date else None,
        last_row,
    )

    if last_date is None or last_row is None:
        LOGGER.error("%s: no dates found", config.name)
        return "no dates found"

    today = dt.date.today()
    if last_date > today:
        LOGGER.info("%s: last date is ahead of today; skipping", config.name)
        return None

    if last_date == today:
        target_row = rows_by_date[today]
        source_row = target_row - 1
        columns = sheet.columns_to_fill(source_row, target_row)
        if not columns:
            LOGGER.info("%s: today's row %s is already complete", config.name, target_row)
            return None
        if dry_run:
            LOGGER.info(
                "DRY_RUN: %s would fill row %s from row %s: %s",
                config.name,
                target_row,
                source_row,
                ", ".join(columns),
            )
            return None
        sheet.copy_columns(source_row, target_row, columns)
        sheet.check_spill_columns(target_row)
        return None

    dates = missing_dates(last_date, today)
    if len(dates) > MAX_BACKFILL_DAYS:
        LOGGER.error(
            "%s: %s missing days exceeds the %s-day safety limit; refusing to backfill",
            config.name,
            len(dates),
            MAX_BACKFILL_DAYS,
        )
        return f"{len(dates)} missing days exceeds the {MAX_BACKFILL_DAYS}-day safety limit"
    if len(dates) > WARN_BACKFILL_DAYS:
        LOGGER.warning("%s: backfilling %s days", config.name, len(dates))

    for value in dates:
        target_row = last_row + 1
        source_row = last_row
        columns = sheet.columns_to_fill(source_row, target_row)
        if dry_run:
            LOGGER.info(
                "DRY_RUN: %s would append %s at row %s and copy: %s",
                config.name,
                value.isoformat(),
                target_row,
                ", ".join(columns) if columns else "(nothing)",
            )
        else:
            sheet.append_date(target_row, value)
            if columns:
                sheet.copy_columns(source_row, target_row, columns)
            else:
                LOGGER.warning("%s: no source columns found on row %s", config.name, source_row)
            sheet.check_spill_columns(target_row)
        last_row = target_row
        last_date = value
    return None


def run(*, dry_run: bool) -> RunResult:
    app = load_app_config()
    failures: list[str] = []
    for config in SHEETS:
        LOGGER.info("=== %s ===", config.name)
        try:
            reason = process_sheet(app, config, dry_run=dry_run)
        except Exception as exc:
            LOGGER.exception("%s failed", config.name)
            failures.append(f"{config.name}: {exc}")
            continue
        if reason:
            failures.append(f"{config.name}: {reason}")

    if failures:
        LOGGER.warning("Failed sheets: %s", "; ".join(failures))

    if not failures:
        LOGGER.info("Done")
    return RunResult("drag", 1 if failures else 0, tuple(failures))
