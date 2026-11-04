"""Fill the linked IEEMA/NALCO sheets up to today's date.

Run this AFTER main.py (CACMAI) and run_balco_declared.py.
Run with:  py run_drag_sheets.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.common.errors import ConfigError, SheetError
from sheet_data_automation.common.logging import setup_logging
from sheet_data_automation.drag_sheets.runner import run

# Set to True to show what would be appended/copied without writing.
DRY_RUN = False

LOGGER = logging.getLogger("sheet_data_automation.drag_sheets")


def main() -> int:
    setup_logging("drag_sheets")
    try:
        return run(dry_run=DRY_RUN).exit_code
    except (ConfigError, SheetError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception:
        LOGGER.exception("Unexpected failure")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
