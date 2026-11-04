"""Run the CACMAI CONDUCTORS automation.

Fills T/U/V/W from NALCO, BALCO and Hindalco, then pulls X:AA formulas down.
Run with:  py main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.cacmai_conductors.runner import run
from sheet_data_automation.common.errors import (
    ConfigError,
    ParseError,
    ScrapeError,
    SheetError,
)
from sheet_data_automation.common.logging import setup_logging

# Set to True to fetch and show the target row without writing to the sheet.
DRY_RUN = False

# Set to False to watch the browser while it clicks each source.
HEADLESS = True

LOGGER = logging.getLogger("sheet_data_automation")


def main() -> int:
    setup_logging("cacmai")
    try:
        return run(dry_run=DRY_RUN, headless=HEADLESS).exit_code
    except (ConfigError, SheetError, ScrapeError, ParseError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception:
        LOGGER.exception("Unexpected failure")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
