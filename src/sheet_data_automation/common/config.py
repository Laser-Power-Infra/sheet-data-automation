from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

BASE_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SPREADSHEET_ID = "1qATwj8rCRpyzpto_-ErKEbjKrEVEfAp0DLGJE7K47Go"

CELL_PATTERN = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
COLUMN_PATTERN = re.compile(r"^[A-Z]{1,3}$")


@dataclass(frozen=True)
class AppConfig:
    spreadsheet_id: str
    service_account_email: str
    service_account_key: str
    logs_dir: Path


def resolve_logs_dir() -> Path:
    load_dotenv(BASE_DIR / ".env")
    raw_logs_dir = os.getenv("LOGS_DIR", "logs").strip() or "logs"
    logs_dir = Path(raw_logs_dir)
    if not logs_dir.is_absolute():
        logs_dir = BASE_DIR / logs_dir
    return logs_dir


def validate_column(value: str, env_var: str) -> str:
    column = value.strip().upper()
    if not COLUMN_PATTERN.fullmatch(column):
        raise ConfigError(f"{env_var} must be a column letter (for example T), got {value!r}")
    return column


def validate_cell(value: str, env_var: str) -> str:
    cell = value.strip().upper()
    if not CELL_PATTERN.fullmatch(cell):
        raise ConfigError(f"{env_var} must be a cell reference (for example T1), got {value!r}")
    return cell


def int_env(value: str, env_var: str, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{env_var} must be an integer, got {value!r}") from exc
    if parsed < minimum:
        raise ConfigError(f"{env_var} must be at least {minimum}, got {parsed}")
    return parsed


def load_app_config(env_file: Path | None = None) -> AppConfig:
    load_dotenv(env_file or BASE_DIR / ".env")

    email = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "").strip()
    key = os.getenv("GOOGLE_PRIVATE_KEY", "").strip().strip('"').replace("\\n", "\n")
    if not email or not key:
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_PRIVATE_KEY must be set in .env")
    if "BEGIN PRIVATE KEY" not in key or "END PRIVATE KEY" not in key:
        raise ConfigError("GOOGLE_PRIVATE_KEY is not a valid PEM private key")

    spreadsheet_id = os.getenv("SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip()
    if not spreadsheet_id:
        raise ConfigError("SPREADSHEET_ID must not be empty")

    return AppConfig(
        spreadsheet_id=spreadsheet_id,
        service_account_email=email,
        service_account_key=key,
        logs_dir=resolve_logs_dir(),
    )
