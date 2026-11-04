"""One-time import of a CACMAI circular PDF into CACMAI CONDUCTORS.

Default is a dry run. Pass --apply to write.

    py run_cacmai_circular_import.py
    py run_cacmai_circular_import.py --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.cacmai_conductors.config import load_cacmai_config
from sheet_data_automation.common.config import load_app_config
from sheet_data_automation.common.errors import ConfigError, ParseError, SheetError
from sheet_data_automation.common.google import open_worksheet
from sheet_data_automation.common.logging import setup_logging
from sheet_data_automation.oneoff.cacmai_circular import (
    build_circular_rows,
    parse_circular_pdf,
    sync_rows,
)

LOGGER = logging.getLogger("sheet_data_automation.oneoff.cacmai_circular")
DEFAULT_PDF = Path(__file__).resolve().parent / "Doc13L-108.pdf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="Circular PDF path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the values. Without this flag the script only prints planned changes.",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging("cacmai_circular_import")
    args = parse_args()
    try:
        data = parse_circular_pdf(args.pdf)
        rows = build_circular_rows(data)
        LOGGER.info(
            "Parsed %s: %s exact dates (%s to %s), %s calendar rows",
            args.pdf.name,
            len(data.dates),
            data.dates[0].isoformat(),
            data.dates[-1].isoformat(),
            len(rows),
        )

        app = load_app_config()
        config = load_cacmai_config()
        worksheet = open_worksheet(app, tab_name=config.tab_name)
        summary = sync_rows(
            worksheet,
            rows,
            date_column=config.date_column,
            apply=args.apply,
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
