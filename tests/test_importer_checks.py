from __future__ import annotations

import datetime as dt

import pytest

from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.oneoff.importers import check_rows

TODAY = dt.date(2026, 11, 16)


def test_good_rows_pass() -> None:
    check_rows({dt.date(2026, 10, 1): {"C": 387650, "E": 2900.5}}, TODAY)


@pytest.mark.parametrize("value", [0, -5, 9_999_999, float("nan"), "12"])
def test_bad_value_rejected(value) -> None:
    with pytest.raises(ParseError, match="Unreasonable value"):
        check_rows({dt.date(2026, 10, 1): {"C": value}}, TODAY)


@pytest.mark.parametrize("day", [dt.date(2030, 1, 1), dt.date(2020, 1, 1)])
def test_bad_dates_rejected(day) -> None:
    with pytest.raises(ParseError, match="look wrong"):
        check_rows({day: {"C": 1}}, TODAY)


def test_empty_rejected() -> None:
    with pytest.raises(ParseError, match="No dates"):
        check_rows({}, TODAY)
