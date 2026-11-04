from __future__ import annotations

import datetime as dt

from sheet_data_automation.drag_sheets.sheet import (
    build_contiguous_ranges,
    filter_missing_columns,
    missing_dates,
    select_dynamic_columns,
)


def test_build_contiguous_ranges_fixed_columns() -> None:
    assert build_contiguous_ranges(("B", "E", "G")) == [(1, 2), (4, 5), (6, 7)]
    assert build_contiguous_ranges(("B", "C", "D")) == [(1, 4)]
    assert build_contiguous_ranges(()) == []


def test_select_dynamic_columns_skips_blanks_and_excluded() -> None:
    values = {
        "A": "22-Oct-2026",
        "B": 102026,
        "C": None,
        "D": 0,
        "E": "",
        "F": 3033,
    }
    assert select_dynamic_columns(values, ("A",)) == ("B", "D", "F")


def test_filter_missing_columns() -> None:
    assert filter_missing_columns(
        ("B", "E", "G"),
        {"B": "PRICE PER MT", "E": None, "G": ""},
    ) == ("E", "G")
    assert (
        filter_missing_columns(
            ("B", "E", "G"),
            {"B": 1, "E": 2, "G": 3},
        )
        == ()
    )


def test_missing_dates_until_today() -> None:
    assert missing_dates(dt.date(2026, 10, 22), dt.date(2026, 10, 23)) == [dt.date(2026, 10, 23)]
    assert missing_dates(dt.date(2026, 10, 21), dt.date(2026, 10, 23)) == [
        dt.date(2026, 10, 22),
        dt.date(2026, 10, 23),
    ]
    assert missing_dates(dt.date(2026, 10, 23), dt.date(2026, 10, 23)) == []
