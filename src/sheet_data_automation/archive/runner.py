from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_ARCHIVE_ROOT,
    ArchiveConfig,
    folder_for,
    form_type_for,
    load_archive_config,
)
from .form import FormAuthError, submit_form, webhook_configured
from .state import State, load_state, save_state
from .storage import filename_for, find_hash, save_pdf, sha256

LOGGER = logging.getLogger(__name__)

DATE_FORMATS = (
    "%d.%m.%Y",
    "%d.%m.%y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d-%B-%Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d %b %Y",
)
URL_DATE_PATTERN = re.compile(r"(\d{1,2})[.\-_](\d{1,2})[.\-_](\d{2,4})")
URL_NAMED_DATE_PATTERN = re.compile(r"(\d{1,2})-([A-Za-z]+)-(\d{4})")


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def iso_date(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def date_from_url(pdf_url: str) -> dt.date | None:
    named = URL_NAMED_DATE_PATTERN.search(pdf_url)
    if named:
        for fmt in ("%d-%B-%Y", "%d-%b-%Y"):
            try:
                return dt.datetime.strptime(
                    f"{named.group(1)}-{named.group(2)}-{named.group(3)}", fmt
                ).date()
            except ValueError:
                continue

    numeric = URL_DATE_PATTERN.search(pdf_url)
    if numeric:
        day, month, year = (int(part) for part in numeric.groups())
        if year < 100:
            year += 2000
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    return None


class ArchiveManager:
    def __init__(self, config: ArchiveConfig | None = None) -> None:
        self.config = config or load_archive_config()
        self.state: State = load_state(self.config.state_file)
        self._webhook_warned = False
        self.failures = 0

    def relative_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.config.root).as_posix()
        except ValueError:
            return str(path)

    def resolve_path(self, stored: str) -> Path:
        """Resolve a state path; old entries hold absolute W:\\ paths."""
        value = stored.replace("\\", "/")
        legacy = str(DEFAULT_ARCHIVE_ROOT).replace("\\", "/").rstrip("/") + "/"
        if value.lower().startswith(legacy.lower()):
            value = value[len(legacy) :]
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.config.root.joinpath(*value.split("/"))

    def retry_pending(self) -> None:
        """Submit every entry still pending from earlier runs."""
        for entry in list(self.state.values()):
            if isinstance(entry, dict) and entry.get("form_status") == "pending":
                try:
                    self._submit(entry)
                except Exception:
                    self.failures += 1
                    LOGGER.exception("Retry failed for %s", entry.get("path"))

    def archive(
        self,
        source: str,
        data: bytes,
        pdf_url: str,
        date_text: str | None,
        run_date: dt.date,
    ) -> None:
        try:
            self._archive(source, data, pdf_url, date_text, run_date)
        except Exception:
            self.failures += 1
            LOGGER.exception("Archive failed for %s (%s)", source, pdf_url)

    def _archive(
        self,
        source: str,
        data: bytes,
        pdf_url: str,
        date_text: str | None,
        run_date: dt.date,
    ) -> None:
        data_date = parse_date(date_text) or date_from_url(pdf_url) or run_date
        folder = folder_for(source, data_date, self.config.root)
        digest = sha256(data)
        existing = find_hash(folder, digest)

        if existing is not None:
            entry = self.state.get(digest)
            if not isinstance(entry, dict):
                entry = self._new_entry(source, data_date, run_date, existing)
                self.state[digest] = entry
                save_state(self.config.state_file, self.state)
                LOGGER.warning("Recovered orphan PDF without state entry: %s", existing)
                self._submit(entry)
            elif entry.get("form_status") == "pending":
                entry["path"] = self.relative_path(existing)
                self._submit(entry)
            return

        filename = filename_for(source, pdf_url)
        path = save_pdf(folder, filename, data)
        LOGGER.info("Saved %s PDF to %s", source, path)

        entry = self._new_entry(source, data_date, run_date, path)
        self.state[digest] = entry
        save_state(self.config.state_file, self.state)
        self._submit(entry)

    def _new_entry(
        self,
        source: str,
        data_date: dt.date,
        run_date: dt.date,
        path: Path,
    ) -> dict[str, Any]:
        return {
            "source": source,
            "circular_date": data_date.isoformat(),
            "form_date": run_date.isoformat(),
            "path": self.relative_path(path),
            "form_status": "pending",
            "attempts": 0,
            "last_error": None,
        }

    def _submit(self, entry: dict[str, Any]) -> None:
        if entry.get("form_status") != "pending":
            return
        if not webhook_configured(self.config):
            if not self._webhook_warned:
                LOGGER.warning(
                    "FORM_WEBHOOK_URL/FORM_WEBHOOK_TOKEN not set; files remain pending."
                )
                self._webhook_warned = True
            return

        path = self.resolve_path(str(entry.get("path", "")))
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        if not path.is_file():
            entry["last_error"] = f"file not found: {path}"
            LOGGER.error("Pending form file not found: %s", path)
            self._give_up_if_needed(entry, path)
            save_state(self.config.state_file, self.state)
            return

        # The sheet's Select Date is the circular's date; state stores ISO dates.
        form_date = (
            iso_date(entry.get("circular_date"))
            or iso_date(entry.get("form_date"))
            or dt.date.today()
        )
        try:
            submit_form(
                self.config,
                form_type_for(str(entry["source"])),
                form_date,
                path,
            )
        except FormAuthError as exc:
            entry["last_error"] = str(exc)
            LOGGER.warning("Form pending: %s", exc)
            self._give_up_if_needed(entry, path)
        except Exception as exc:  # noqa: BLE001
            entry["last_error"] = str(exc)
            LOGGER.error("Form submission failed for %s: %s", path, exc)
            self._give_up_if_needed(entry, path)
        else:
            entry["form_status"] = "submitted"
            entry["last_error"] = None
            LOGGER.info("Form marked submitted for %s", path)
        save_state(self.config.state_file, self.state)

    def _give_up_if_needed(self, entry: dict[str, Any], path: Path) -> None:
        if entry["attempts"] >= self.config.max_attempts:
            entry["form_status"] = "failed"
            LOGGER.error("Giving up on %s after %s attempts", path, entry["attempts"])
