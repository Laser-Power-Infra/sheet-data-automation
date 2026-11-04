from __future__ import annotations

import pytest

from sheet_data_automation.archive.config import load_archive_config
from sheet_data_automation.balco_declared.config import load_balco_declared_config
from sheet_data_automation.cacmai_conductors.config import load_cacmai_config
from sheet_data_automation.common.config import load_app_config
from sheet_data_automation.common.errors import ConfigError


def test_invalid_column_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICE_COLUMN", "T!")
    with pytest.raises(ConfigError, match="PRICE_COLUMN"):
        load_cacmai_config()


def test_invalid_cell_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINK_CELL", "T0")
    with pytest.raises(ConfigError, match="LINK_CELL"):
        load_cacmai_config()


def test_invalid_gid_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BALCO_DECLARED_GID", "not-a-number")
    with pytest.raises(ConfigError, match="BALCO_DECLARED_GID"):
        load_balco_declared_config()


def test_invalid_private_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "x@example.com")
    monkeypatch.setenv("GOOGLE_PRIVATE_KEY", "not-a-key")
    with pytest.raises(ConfigError, match="GOOGLE_PRIVATE_KEY"):
        load_app_config()


def test_invalid_max_attempts_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORM_MAX_ATTEMPTS", "0")
    with pytest.raises(ConfigError, match="FORM_MAX_ATTEMPTS"):
        load_archive_config()


def test_invalid_webhook_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORM_WEBHOOK_URL", "ftp://example.com")
    with pytest.raises(ConfigError, match="FORM_WEBHOOK_URL"):
        load_archive_config()
