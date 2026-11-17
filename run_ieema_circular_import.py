"""One-time import of an IEEMA conductor circular PDF into IEEMA CONDUCTOR.

Default is a dry run. Pass --apply to write.

    py run_ieema_circular_import.py
    py run_ieema_circular_import.py --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.common.config import load_app_config
from sheet_data_automation.common.errors import ConfigError, ParseError, SheetError
from sheet_data_automation.common.google import open_worksheet
from sheet_data_automation.common.logging import setup_logging
from sheet_data_automation.oneoff.cacmai_circular import sync_rows
from sheet_data_automation.oneoff.ieema_circular import (
    TARGET_COLUMNS,
    build_ieema_rows,
    parse_ieema_pdf,
)

LOGGER = logging.getLogger("sheet_data_automation.oneoff.ieema_circular")
DEFAULT_PDF = Path(__file__).resolve().parent / "01-10-2026.pdf"
TAB_NAME = "IEEMA CONDUCTOR"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="Circular PDF path")
    parser.add_argument("--apply", action="store_true", help="Write the values (default: dry run)")
    return parser.parse_args()


def main() -> int:
    setup_logging("ieema_circular_import")
    args = parse_args()
    try:
        data = parse_ieema_pdf(args.pdf)
        rows = build_ieema_rows(data)
        LOGGER.info(
            "Parsed %s: %s exact dates (%s to %s), %s calendar rows",
            args.pdf.name,
            len(data.dates),
            data.dates[0].isoformat(),
            data.dates[-1].isoformat(),
            len(rows),
        )
        worksheet = open_worksheet(load_app_config(), tab_name=TAB_NAME)
        summary = sync_rows(
            worksheet,
            rows,
            apply=args.apply,
            columns=TARGET_COLUMNS,
            backup_prefix="ieema-import",
        )
        LOGGER.info(
            "Summary: dates=%s rows=%s cells=%s missing=%s%s",
            summary["dates"],
            summary["rows"],
            summary["cells"],
            summary["missing"],
            "" if args.apply else " (dry run)",
        )
        return 0
    except (ConfigError, ParseError, SheetError, OSError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception:
        LOGGER.exception("Unexpected failure")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
