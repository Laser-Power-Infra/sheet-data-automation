from __future__ import annotations

import datetime as dt

import pytest

from sheet_data_automation.balco_declared.rbi import format_rbi_date, parse_rbi_rate
from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.common.google import is_filled
from sheet_data_automation.common.values import decide_value, previous_value

USD_TABLE = """
Date

USD (INR / 1 USD)

22/10/2026	94.6986
"""


def test_format_rbi_date() -> None:
    assert format_rbi_date(dt.date(2026, 10, 2)) == "02/10/2026"


def test_parses_usd_rate() -> None:
    assert parse_rbi_rate(USD_TABLE, "22/10/2026") == 94.6986


def test_no_rate_found_returns_none() -> None:
    assert parse_rbi_rate("No Reference Rate Found.", "25/10/2026") is None


def test_date_mismatch_returns_none() -> None:
    assert parse_rbi_rate(USD_TABLE, "23/10/2026") is None


def test_zero_rate_raises() -> None:
    with pytest.raises(ParseError):
        parse_rbi_rate("22/10/2026\t0", "22/10/2026")


def test_is_filled() -> None:
    assert is_filled(94.6986)
    assert is_filled("94.6986")
    assert not is_filled(None)
    assert not is_filled("")
    assert not is_filled("  ")


class FakeSheet:
    def __init__(self, rates: dict[int, object]) -> None:
        self.rates = rates

    def read_rate(self, row: int) -> object:
        return self.rates.get(row)


def test_decide_value_cases() -> None:
    assert decide_value(None, None, 94.9) == (94.9, "filled")
    assert decide_value(94.9, None, 94.9) == (None, "unchanged")
    assert decide_value(94.7, None, 94.9) == (94.9, "updated")
    assert decide_value(94.9, 94.7, None) == (None, "keep")
    assert decide_value(None, 94.7, None) == (94.7, "carried")
    assert decide_value(None, None, None) == (None, "empty")


def test_previous_value_scans_upward() -> None:
    sheet = FakeSheet({8: 94.7})
    assert previous_value(lambda r: sheet.read_rate(r), 10, limit=3) == (94.7, 8)  # type: ignore[arg-type]


def test_previous_value_missing() -> None:
    sheet = FakeSheet({})
    assert previous_value(lambda r: sheet.read_rate(r), 10, limit=3) == (None, None)  # type: ignore[arg-type]
    assert previous_value(lambda r: sheet.read_rate(r), 1, limit=3) == (None, None)  # type: ignore[arg-type]
