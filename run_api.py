"""Run the FastAPI service for scheduled sheet automation.

Local:  py run_api.py
Docker: python run_api.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sheet_data_automation.common.logging import setup_logging

LOGGER = logging.getLogger("sheet_data_automation.api")


def main() -> int:
    setup_logging("api")
    try:
        port = int(os.getenv("API_PORT", "8000"))
    except ValueError:
        LOGGER.error("API_PORT must be an integer, got %r", os.getenv("API_PORT"))
        return 1

    import uvicorn

    uvicorn.run(
        "sheet_data_automation.api.app:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
        timeout_graceful_shutdown=60,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
