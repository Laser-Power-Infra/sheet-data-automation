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


def test_backfill_gap_rates_only_weekdays_and_keeps_carry_on_failure(monkeypatch) -> None:
    import datetime as dt
    from types import SimpleNamespace

    from sheet_data_automation.balco_declared import runner
    from sheet_data_automation.common.errors import ScrapeError

    calls: list[dt.date] = []

    def fake_lookup(link, day, session, *, logs_dir=None):
        calls.append(day)
        if day == dt.date(2026, 10, 29):
            raise ScrapeError("down")
        return 95.1

    monkeypatch.setattr(runner, "lookup_usd_rate", fake_lookup)
    sheet = SimpleNamespace(
        config=SimpleNamespace(link_cell="E1", rate_column="E"),
        read_link=lambda cell: "https://rbi",
    )
    writes: dict[int, dict[str, object]] = {}
    gaps = {
        dt.date(2026, 10, 25): 10,  # Sunday: carried, no lookup
        dt.date(2026, 10, 29): 11,  # Thursday: lookup fails, carried
        dt.date(2026, 10, 30): 12,  # Friday: real rate
    }
    runner.backfill_gap_rates(sheet, gaps, writes, session=None)
    assert calls == [dt.date(2026, 10, 29), dt.date(2026, 10, 30)]
    assert writes == {12: {"E": 95.1}}
