from __future__ import annotations

from sheet_data_automation.balco_declared.sheet import (
    BALCO_FILL_COLUMNS,
    build_fill_ranges,
    row_needs_fill,
)


def test_build_fill_ranges_excludes_inserted_columns_and_ab() -> None:
    assert build_fill_ranges(("A", "C", "E", "R", "X")) == [
        (1, 2),
        (3, 4),
        (5, 17),
        (18, 23),
        (24, 27),
    ]


def test_build_fill_ranges_with_no_inserted_columns() -> None:
    assert build_fill_ranges(()) == [(0, 27)]


def test_row_needs_fill() -> None:
    assert row_needs_fill({}, BALCO_FILL_COLUMNS)
    assert not row_needs_fill(
        {column: 1 for column in BALCO_FILL_COLUMNS},
        BALCO_FILL_COLUMNS,
    )
    values: dict[str, object] = {column: 1 for column in BALCO_FILL_COLUMNS}
    values["U"] = ""
    assert row_needs_fill(values, BALCO_FILL_COLUMNS)
