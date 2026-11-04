from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import resolve_logs_dir

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(name: str) -> None:
    """Configure console + rotating file logging once per process."""
    root = logging.getLogger()
    if getattr(root, "_sheet_automation_configured", False):
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    logs_dir = resolve_logs_dir()
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            logs_dir / f"{_safe_name(name)}.log",
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        logging.getLogger(__name__).warning("File logging disabled: %s", exc)

    root._sheet_automation_configured = True  # type: ignore[attr-defined]


def _safe_name(name: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in name)
    return safe.strip("-") or "app"


__all__ = ["setup_logging"]
