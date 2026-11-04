from __future__ import annotations

import datetime as dt
import logging

from ..archive.runner import ArchiveManager
from ..common.browser import browser_session
from ..common.config import load_app_config
from ..common.errors import ParseError, ScrapeError
from ..common.google import FIRST_DATA_ROW, is_filled
from ..common.result import RunResult
from ..common.values import decide_value, previous_value
from .balco import fetch_balco_prices
from .config import CacmaiConfig, load_cacmai_config
from .hindalco import fetch_hindalco_price
from .nalco import fetch_ingot_price
from .sheet import PriceSheet

LOGGER = logging.getLogger("sheet_data_automation")


def required_columns(config: CacmaiConfig) -> tuple[str, ...]:
    return (
        config.price_column,
        config.balco_cg_column,
        config.hindalco_column,
        config.vedanta_column,
    )


def collect_prices(
    sheet: PriceSheet,
    config: CacmaiConfig,
    *,
    headless: bool,
    archive: ArchiveManager | None,
    run_date: dt.date,
) -> tuple[dict[str, int], list[str]]:
    values: dict[str, int] = {}
    failures: list[str] = []

    with browser_session(headless=headless) as session:
        try:
            nalco = fetch_ingot_price(
                sheet.read_link(config.link_cell),
                session,
                logs_dir=sheet.app.logs_dir,
                on_pdf=(
                    lambda data, url, date: (
                        archive.archive("NALCO", data, url, date, run_date) if archive else None
                    )
                ),
            )
            values[config.price_column] = nalco.price
        except (ScrapeError, ParseError, ValueError) as exc:
            failures.append("NALCO")
            LOGGER.error("NALCO failed: %s", exc)

        try:
            balco = fetch_balco_prices(
                sheet.read_link(config.balco_link_cell),
                session,
                logs_dir=sheet.app.logs_dir,
                on_pdf=(
                    lambda data, url, date: (
                        archive.archive("BALCO", data, url, date, run_date) if archive else None
                    )
                ),
            )
            values[config.balco_cg_column] = balco.cg99
            values[config.vedanta_column] = balco.ec_cg
        except (ScrapeError, ParseError, ValueError) as exc:
            failures.append("BALCO")
            LOGGER.error("BALCO failed: %s", exc)

        try:
            hindalco = fetch_hindalco_price(
                sheet.read_link(config.hindalco_link_cell),
                session,
                logs_dir=sheet.app.logs_dir,
                on_pdf=(
                    lambda data, url, date: (
                        archive.archive("HINDALCO", data, url, date, run_date) if archive else None
                    )
                ),
            )
            values[config.hindalco_column] = hindalco.price
        except (ScrapeError, ParseError, ValueError) as exc:
            failures.append("Hindalco")
            LOGGER.error("Hindalco failed: %s", exc)

    return values, failures


def previous_column_value(
    sheet: PriceSheet,
    row: int,
    column: str,
) -> tuple[object | None, int | None]:
    return previous_value(
        lambda candidate: sheet.read_values(candidate, (column,)).get(column),
        row,
    )


def fill_formula_rows(sheet: PriceSheet, rows: list[int]) -> bool:
    success = True
    for row in sorted(set(rows)):
        try:
            sheet.fill_down_formulas(row)
        except Exception:
            LOGGER.exception("B/X:AA fill-down failed for row %s", row)
            success = False
    return success


def run(*, dry_run: bool, headless: bool) -> RunResult:
    app = load_app_config()
    config = load_cacmai_config()
    sheet = PriceSheet(app, config)
    required = required_columns(config)

    run_date = dt.date.today()
    try:
        target = sheet.find_target_row(run_date, dry_run=dry_run)
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return RunResult("cacmai", 1, (str(exc),))

    previous_row = target.row - 1 if target.row - 1 >= FIRST_DATA_ROW else None
    previous_needs_repair = False
    if (
        previous_row is not None
        and not sheet.missing_values(previous_row, required)
        and not sheet.formulas_complete(previous_row)
    ):
        previous_needs_repair = True
        LOGGER.info(
            "Row %s has T/U/V/W but B/X:AA is missing; formulas will be filled",
            previous_row,
        )

    current_values = sheet.read_values(target.row, required)
    archive = None if dry_run else ArchiveManager()
    if archive is not None:
        archive.retry_pending()
    values, failures = collect_prices(
        sheet,
        config,
        headless=headless,
        archive=archive,
        run_date=run_date,
    )

    writes: dict[str, object] = {}
    for column in required:
        current = current_values.get(column)
        previous, previous_value_row = previous_column_value(sheet, target.row, column)
        fetched = values.get(column)
        value, action = decide_value(current, previous, fetched)

        if action == "unchanged":
            LOGGER.info("%s%s unchanged (%s)", column, target.row, current)
        elif action == "updated":
            LOGGER.info("%s%s updated: %s -> %s", column, target.row, current, value)
        elif action == "filled":
            LOGGER.info("%s%s = %s", column, target.row, value)
        elif action == "carried":
            LOGGER.info(
                "%s%s carried forward %s from row %s",
                column,
                target.row,
                value,
                previous_value_row,
            )
        elif action == "keep":
            LOGGER.info("%s%s kept (%s)", column, target.row, current)
        else:
            LOGGER.info("%s%s has no value and no previous value", column, target.row)

        if value is not None:
            writes[column] = value

    effective_values = {
        column: writes.get(column, current_values.get(column)) for column in required
    }
    all_present = all(is_filled(value) for value in effective_values.values())
    missing_required = [
        column for column in required if not is_filled(effective_values.get(column))
    ]
    if missing_required:
        message = f"missing values: {', '.join(missing_required)}"
        failures.append(message)
        LOGGER.error("Row %s is missing required values: %s", target.row, ", ".join(missing_required))

    repair_rows: list[int] = []
    if previous_needs_repair and previous_row is not None:
        repair_rows.append(previous_row)
    if all_present and not sheet.formulas_complete(target.row):
        repair_rows.append(target.row)
        LOGGER.info(
            "Row %s has T/U/V/W but B/X:AA is missing; formulas will be filled",
            target.row,
        )

    if dry_run:
        if target.existing:
            if writes:
                LOGGER.info(
                    "DRY_RUN: would write row %s: %s",
                    target.row,
                    ", ".join(f"{column}={value}" for column, value in sorted(writes.items())),
                )
            else:
                LOGGER.info("DRY_RUN: no value changes for row %s", target.row)
        else:
            LOGGER.info(
                "DRY_RUN: would append row %s with date %s and values: %s",
                target.row,
                run_date.isoformat(),
                ", ".join(f"{column}={value}" for column, value in sorted(writes.items())),
            )
        if repair_rows:
            LOGGER.info("DRY_RUN: would fill B/X:AA for row(s) %s", repair_rows)
        return RunResult("cacmai", 1 if failures else 0, tuple(failures))

    if target.existing:
        if writes:
            sheet.write_row(target, run_date, writes)
        else:
            LOGGER.info("No value changes for row %s", target.row)
    else:
        if writes:
            sheet.write_row(target, run_date, writes)
        else:
            sheet.write_date(target.row, run_date)

    if repair_rows and not fill_formula_rows(sheet, repair_rows):
        failures.append("B/X:AA fill-down")

    if failures:
        LOGGER.warning("Failures: %s", ", ".join(failures))

    if archive is not None and archive.failures:
        failures.append(f"archive: {archive.failures}")
        LOGGER.warning("Archive failures: %s", archive.failures)

    if not failures:
        LOGGER.info("Done")
    return RunResult("cacmai", 1 if failures else 0, tuple(failures))
