from __future__ import annotations

import datetime as dt
import logging

from ..common.browser import browser_session
from ..common.config import load_app_config
from ..common.errors import ParseError, ScrapeError
from ..common.google import backfill_gap_rows, choose_target_row, is_filled, scan_dates
from ..common.result import RunResult
from ..common.values import decide_value, previous_value, same_number
from .config import load_balco_declared_config
from .lme import LmeQuote, fetch_quote, lme_sources
from .rbi import lookup_usd_rate
from .sheet import BALCO_FILL_COLUMNS, BalcoDeclaredSheet

LOGGER = logging.getLogger("sheet_data_automation.balco_declared")


def previous_column_value(
    sheet: BalcoDeclaredSheet,
    row: int,
    column: str,
) -> tuple[object | None, int | None]:
    return previous_value(
        lambda candidate: sheet.read_values(candidate, (column,)).get(column),
        row,
    )


def log_decision(
    label: str,
    column: str,
    row: int,
    action: str,
    current: object,
    value: object,
    previous_row: int | None,
) -> None:
    if action == "unchanged":
        LOGGER.info("%s %s%s unchanged (%s)", label, column, row, current)
    elif action == "updated":
        LOGGER.info("%s %s%s updated: %s -> %s", label, column, row, current, value)
    elif action == "filled":
        LOGGER.info("%s %s%s = %s", label, column, row, value)
    elif action == "carried":
        LOGGER.info(
            "%s %s%s carried forward %s from row %s",
            label,
            column,
            row,
            value,
            previous_row,
        )
    elif action == "keep":
        LOGGER.info("%s %s%s kept (%s)", label, column, row, current)
    else:
        LOGGER.info("%s %s%s has no value and no previous value", label, column, row)


def run(
    *,
    dry_run: bool,
    headless: bool,
    date_override: dt.date | None = None,
) -> RunResult:
    app = load_app_config()
    config = load_balco_declared_config()
    sheet = BalcoDeclaredSheet(app, config)

    run_date = date_override or dt.date.today()
    rows_by_date, last_row, last_date = scan_dates(sheet.worksheet, config.date_column)
    today_row = rows_by_date.get(run_date)

    try:
        if today_row is None and last_date is not None and last_date < run_date:
            last_row = backfill_gap_rows(
                sheet.worksheet, last_row, last_date, run_date, dry_run=dry_run
            )
            last_date = max(last_date, run_date - dt.timedelta(days=1))
        target = choose_target_row(today_row, last_row, last_date, run_date)
    except ValueError as exc:
        LOGGER.error("%s", exc)
        return RunResult("balco", 1, (str(exc),))

    LOGGER.info(
        "Last sheet date: %s (row %s) -> row %s for %s%s",
        last_date.isoformat() if last_date else None,
        last_row,
        target.row,
        run_date.isoformat(),
        " (existing)" if target.existing else " (new date row)",
    )

    writes: dict[int, dict[str, object]] = {}
    failures: list[str] = []

    current_rate = sheet.read_rate(target.row)
    previous_rate, previous_rate_row = previous_column_value(sheet, target.row, config.rate_column)

    if not target.existing:
        if dry_run:
            LOGGER.info(
                "DRY_RUN: would append date %s to %s%s",
                run_date,
                config.date_column,
                target.row,
            )
        else:
            LOGGER.info(
                "Appending date %s to %s%s (date only)",
                run_date,
                config.date_column,
                target.row,
            )
            sheet.write_date(target.row, run_date)

    sources = lme_sources(config)
    metal_columns = tuple(source.column for source in sources)
    fetched_metals: dict[str, LmeQuote | None] = {}

    with browser_session(headless=headless) as session:
        fetched_rate: float | None = None
        try:
            fetched_rate = lookup_usd_rate(
                sheet.read_link(config.link_cell),
                run_date,
                session,
                logs_dir=app.logs_dir,
            )
        except (ScrapeError, ParseError, ValueError) as exc:
            failures.append("RBI")
            LOGGER.error("RBI failed: %s", exc)

        value, action = decide_value(current_rate, previous_rate, fetched_rate)
        log_decision(
            "RBI",
            config.rate_column,
            target.row,
            action,
            current_rate,
            value,
            previous_rate_row,
        )
        if value is not None:
            writes.setdefault(target.row, {})[config.rate_column] = value

        for source in sources:
            try:
                quote = fetch_quote(
                    source,
                    sheet.read_link(source.link_cell),
                    session,
                    logs_dir=app.logs_dir,
                )
                if quote is None:
                    LOGGER.info(
                        "No LME %s Cash Offer; %s left unchanged",
                        source.metal,
                        source.column,
                    )
                fetched_metals[source.column] = quote
            except (ScrapeError, ParseError, ValueError) as exc:
                failures.append(source.metal)
                fetched_metals[source.column] = None
                LOGGER.error("LME %s failed: %s", source.metal, exc)

    for source in sources:
        column = source.column
        quote = fetched_metals.get(column)
        fetched = quote.value if quote is not None else None

        if quote is not None:
            data_row = rows_by_date.get(quote.data_date)
            if data_row is not None:
                current_data = sheet.read_values(data_row, (column,)).get(column)
                if not same_number(current_data, quote.value):
                    writes.setdefault(data_row, {})[column] = quote.value
                    LOGGER.info(
                        "LME %s row %s updated: %s -> %s",
                        source.metal,
                        data_row,
                        current_data,
                        quote.value,
                    )

        current = sheet.read_values(target.row, (column,)).get(column)
        previous, previous_row = previous_column_value(sheet, target.row, column)
        value, action = decide_value(current, previous, fetched)
        log_decision(source.metal, column, target.row, action, current, value, previous_row)
        if value is not None:
            writes.setdefault(target.row, {})[column] = value

    required = (config.rate_column, *metal_columns)
    current_target = sheet.read_values(target.row, required)
    planned = writes.get(target.row, {})
    missing_required = [
        column
        for column in required
        if not is_filled(planned.get(column)) and not is_filled(current_target.get(column))
    ]
    if missing_required:
        message = f"missing values: {', '.join(missing_required)}"
        failures.append(message)
        LOGGER.error("Row %s is missing required values: %s", target.row, ", ".join(missing_required))

    if dry_run:
        if not writes:
            LOGGER.info("DRY_RUN: no changes needed")
        for row, values in sorted(writes.items()):
            LOGGER.info(
                "DRY_RUN: would write row %s: %s",
                row,
                ", ".join(f"{column}={value}" for column, value in sorted(values.items())),
            )

        current = sheet.read_values(target.row, metal_columns)
        planned = writes.get(target.row, {})
        has_metal = any(
            is_filled(planned.get(column)) or is_filled(current.get(column))
            for column in metal_columns
        )
        if has_metal and sheet.needs_fill(target.row, BALCO_FILL_COLUMNS):
            LOGGER.info(
                "DRY_RUN: would copy non-inserted columns from row %s to row %s",
                target.row - 1,
                target.row,
            )
        return RunResult("balco", 1 if failures else 0, tuple(failures))

    for row, values in sorted(writes.items()):
        sheet.write_values(row, values)

    inserted_columns = (
        config.date_column,
        config.rate_column,
        *metal_columns,
    )
    metal_values = sheet.read_values(target.row, metal_columns)
    if any(is_filled(value) for value in metal_values.values()):
        try:
            sheet.fill_other_columns(target.row, inserted_columns)
        except Exception:
            LOGGER.exception("Row values were written, but fill-down failed")
            failures.append("fill-down")
    else:
        LOGGER.info("No metal prices present; skipping fill-down")

    if failures:
        LOGGER.warning("Partial update; failures: %s", ", ".join(failures))

    if not writes:
        LOGGER.info("No changes needed")
    if not failures:
        LOGGER.info("Done")
    return RunResult("balco", 1 if failures else 0, tuple(failures))
