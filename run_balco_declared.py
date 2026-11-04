"""Run the BALCO DECLARED automation.

Looks up today's RBI USD reference rate and writes it to column E.
Run with:  py run_balco_declared.py
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.balco_declared.runner import run
from sheet_data_automation.common.errors import (
    ConfigError,
    ParseError,
    ScrapeError,
    SheetError,
)
from sheet_data_automation.common.logging import setup_logging

# Set to True to look up the rate without writing to the sheet.
DRY_RUN = False

# Set to False to watch the browser.
HEADLESS = True

# Optional ISO date override for debugging, e.g. "2026-10-21".
DATE_OVERRIDE: str | None = None

LOGGER = logging.getLogger("sheet_data_automation.balco_declared")


def main() -> int:
    setup_logging("balco_declared")
    try:
        try:
            date_override = dt.date.fromisoformat(DATE_OVERRIDE) if DATE_OVERRIDE else None
        except ValueError:
            LOGGER.error("DATE_OVERRIDE must be YYYY-MM-DD, got %r", DATE_OVERRIDE)
            return 1
        return run(
            dry_run=DRY_RUN,
            headless=HEADLESS,
            date_override=date_override,
        ).exit_code
    except (ConfigError, SheetError, ScrapeError, ParseError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception:
        LOGGER.exception("Unexpected failure")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
