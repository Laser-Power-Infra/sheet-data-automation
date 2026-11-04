from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from ..common.config import BASE_DIR, int_env
from ..common.errors import ConfigError

DEFAULT_ARCHIVE_ROOT = Path(r"W:\ALU price history")
DEFAULT_MAX_ATTEMPTS = 10


@dataclass(frozen=True)
class ArchiveConfig:
    root: Path
    state_file: Path
    webhook_url: str = ""
    webhook_token: str = ""
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


def load_archive_config() -> ArchiveConfig:
    root = Path(os.getenv("ARCHIVE_ROOT", str(DEFAULT_ARCHIVE_ROOT)))
    state_file = Path(
        os.getenv("ARCHIVE_STATE_FILE", str(BASE_DIR / "state" / "archive_state.json"))
    )
    webhook_url = os.getenv("FORM_WEBHOOK_URL", "").strip()
    if webhook_url and not webhook_url.startswith(("http://", "https://")):
        raise ConfigError("FORM_WEBHOOK_URL must start with http:// or https://")
    return ArchiveConfig(
        root=root,
        state_file=state_file,
        webhook_url=webhook_url,
        webhook_token=os.getenv("FORM_WEBHOOK_TOKEN", "").strip(),
        max_attempts=int_env(
            os.getenv("FORM_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS)),
            "FORM_MAX_ATTEMPTS",
            minimum=1,
        ),
    )


def nalco_fiscal_year(value: dt.date) -> str:
    fiscal_start = value.year if value.month >= 4 else value.year - 1
    return f"{fiscal_start}-{str(fiscal_start + 1)[-2:]}"


def folder_for(source: str, value: dt.date, root: Path) -> Path:
    if source == "BALCO":
        return root / "Balco2" / value.strftime("%b %Y")
    if source == "HINDALCO":
        # shortcut: 2026 and earlier keep the old month-only folders; 2027+ get "Jan 2027".
        return root / "HINDALCO2" / value.strftime("%b" if value.year <= 2026 else "%b %Y")
    if source == "NALCO":
        return root / "NALCO" / nalco_fiscal_year(value) / value.strftime("%b")
    raise ValueError(f"Unknown archive source: {source}")


def suffix_for(source: str) -> str:
    if source == "BALCO":
        return " Balco.pdf"
    if source == "HINDALCO":
        return " Hindalco.pdf"
    if source == "NALCO":
        return " Nalco.pdf"
    raise ValueError(f"Unknown archive source: {source}")


def form_type_for(source: str) -> str:
    if source == "BALCO":
        return "Balco"
    if source == "HINDALCO":
        return "Hindalco"
    if source == "NALCO":
        return "Nalco"
    raise ValueError(f"Unknown archive source: {source}")
