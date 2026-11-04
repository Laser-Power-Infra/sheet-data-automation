from __future__ import annotations

import datetime as dt

import pytest

from sheet_data_automation.cacmai_conductors.formulas import (
    build_formula_fill_request,
    has_complete_formulas,
    is_formula_values,
)
from sheet_data_automation.cacmai_conductors.sheet import build_row_updates
from sheet_data_automation.common.google import (
    FIRST_DATA_ROW,
    backfill_gap_rows,
    choose_target_row,
    column_index,
    from_serial,
    is_filled,
    missing_columns,
    read_columns,
    to_serial,
)


def test_serial_round_trip() -> None:
    value = dt.date(2026, 10, 21)
    assert to_serial(value) == 46316
    assert from_serial(to_serial(value)) == value


def test_from_serial_ignores_non_dates() -> None:
    assert from_serial(None) is None
    assert from_serial("") is None
    assert from_serial("not a date") is None
    assert from_serial(0) is None
    assert from_serial(float("nan")) is None
    assert from_serial(1_000_000) is None


def test_appends_after_last_date() -> None:
    target = choose_target_row(None, 3585, dt.date(2026, 10, 21), dt.date(2026, 10, 22))
    assert target.row == 3586
    assert target.existing is False


def test_updates_same_day() -> None:
    target = choose_target_row(3586, 3586, dt.date(2026, 10, 22), dt.date(2026, 10, 22))
    assert target.row == 3586
    assert target.existing is True


def test_uses_today_row_when_sheet_is_ahead() -> None:
    target = choose_target_row(3586, 3587, dt.date(2026, 10, 23), dt.date(2026, 10, 22))
    assert target.row == 3586
    assert target.existing is True


def test_refuses_out_of_order_append() -> None:
    with pytest.raises(ValueError, match="ahead"):
        choose_target_row(None, 3587, dt.date(2026, 10, 23), dt.date(2026, 10, 22))


def test_starts_at_first_data_row_when_empty() -> None:
    target = choose_target_row(None, None, None, dt.date(2026, 10, 22))
    assert target.row == FIRST_DATA_ROW
    assert target.existing is False


class _FakeSpreadsheet:
    def __init__(self) -> None:
        self.bodies: list[dict] = []

    def batch_update(self, body: dict) -> None:
        self.bodies.append(body)


class _FakeWorksheet:
    id = 7
    title = "BALCO DECLARED"

    def __init__(self) -> None:
        self.spreadsheet = _FakeSpreadsheet()


def test_backfill_carries_previous_row_into_missed_dates() -> None:
    # 24-Oct is the last row (3221); the job missed 25-Oct and runs on 26-Oct.
    ws = _FakeWorksheet()
    new_last = backfill_gap_rows(ws, 3221, dt.date(2026, 10, 24), dt.date(2026, 10, 26))
    assert new_last == 3222
    copy, date_cell = ws.spreadsheet.bodies[0]["requests"]
    assert copy["copyPaste"]["source"]["startRowIndex"] == 3220
    assert copy["copyPaste"]["destination"]["startRowIndex"] == 3221
    assert copy["copyPaste"]["destination"]["endColumnIndex"] == column_index("AA")
    assert date_cell["updateCells"]["start"]["rowIndex"] == 3221
    value = date_cell["updateCells"]["rows"][0]["values"][0]["userEnteredValue"]["numberValue"]
    assert from_serial(value) == dt.date(2026, 10, 25)
    # Next day's append now lands after the carried row.
    assert choose_target_row(None, new_last, dt.date(2026, 10, 25), dt.date(2026, 10, 26)).row == 3223


def test_backfill_noop_without_gap_or_in_dry_run() -> None:
    ws = _FakeWorksheet()
    assert backfill_gap_rows(ws, 3221, dt.date(2026, 10, 24), dt.date(2026, 10, 25)) == 3221
    assert backfill_gap_rows(ws, 3221, dt.date(2026, 10, 24), dt.date(2026, 10, 27), dry_run=True) == 3223
    assert ws.spreadsheet.bodies == []


def test_backfill_refuses_gap_over_safety_limit() -> None:
    ws = _FakeWorksheet()
    with pytest.raises(ValueError, match="safety limit"):
        backfill_gap_rows(ws, 100, dt.date(2024, 1, 1), dt.date(2026, 10, 26))
    assert ws.spreadsheet.bodies == []


def test_build_row_updates_maps_columns() -> None:
    values = {"T": 335750, "U": 339250, "V": 336000, "W": 340000}
    updates = build_row_updates(3586, dt.date(2026, 10, 22), values)

    assert updates[0] == {"range": "A3586", "values": [["2026-10-22"]]}
    assert {item["range"]: item["values"][0][0] for item in updates[1:]} == {
        "T3586": 335750,
        "U3586": 339250,
        "V3586": 336000,
        "W3586": 340000,
    }


def test_column_index_for_formula_columns() -> None:
    assert column_index("X") == 24
    assert column_index("AA") == 27


def test_is_formula_values_requires_four_formulas() -> None:
    assert is_formula_values(["=AVERAGE(A1:D1)", "=B1", "=C1+D1", "=E1+1"])
    assert not is_formula_values(["=AVERAGE(A1:D1)", "=B1", "=C1+D1"])
    assert not is_formula_values(["=AVERAGE(A1:D1)", "=B1", "=C1+D1", "123"])


def test_build_formula_fill_request_includes_b_and_x_to_aa() -> None:
    body = build_formula_fill_request(1641776042, 3585, 3586)
    assert len(body["requests"]) == 2

    b_request = body["requests"][0]["copyPaste"]
    assert b_request["source"] == {
        "sheetId": 1641776042,
        "startRowIndex": 3584,
        "endRowIndex": 3585,
        "startColumnIndex": 1,
        "endColumnIndex": 2,
    }
    assert b_request["destination"] == {
        "sheetId": 1641776042,
        "startRowIndex": 3585,
        "endRowIndex": 3586,
        "startColumnIndex": 1,
        "endColumnIndex": 2,
    }

    request = body["requests"][1]["copyPaste"]
    assert request["source"] == {
        "sheetId": 1641776042,
        "startRowIndex": 3584,
        "endRowIndex": 3585,
        "startColumnIndex": 23,
        "endColumnIndex": 27,
    }
    assert request["destination"] == {
        "sheetId": 1641776042,
        "startRowIndex": 3585,
        "endRowIndex": 3586,
        "startColumnIndex": 23,
        "endColumnIndex": 27,
    }
    assert request["pasteType"] == "PASTE_NORMAL"
    assert request["pasteOrientation"] == "NORMAL"


class FakeWorksheet:
    def __init__(self, cells: list[object], b_value: object = "=A1") -> None:
        self.cells = cells
        self.b_value = b_value

    def get(self, range_name: str, **kwargs: object) -> list[list[object]]:
        return [self.cells]

    def acell(self, range_name: str, **kwargs: object) -> object:
        return type("Cell", (), {"value": self.b_value})()


def test_read_columns_handles_trailing_blanks() -> None:
    worksheet = FakeWorksheet([335750, 339250])
    values = read_columns(worksheet, 3587, ("T", "U", "V", "W"))  # type: ignore[arg-type]

    assert values == {"T": 335750, "U": 339250, "V": None, "W": None}
    assert missing_columns(values, ("T", "U", "V", "W")) == ["V", "W"]


def test_missing_columns_when_all_filled() -> None:
    values = {"T": 335750, "U": 339250, "V": 336000, "W": 340000}
    assert missing_columns(values, ("T", "U", "V", "W")) == []


def test_has_complete_formulas() -> None:
    complete = FakeWorksheet(["=AVERAGE(T1:W1)", "=S1", "=T1", "=Z2"], "=MONTH(A1)")
    partial = FakeWorksheet(["=AVERAGE(T1:W1)", "=S1", "", "=Z2"], "=MONTH(A1)")
    missing_b = FakeWorksheet(["=AVERAGE(T1:W1)", "=S1", "=T1", "=Z2"], "")
    static = FakeWorksheet([1, 2, 3, 4], "=MONTH(A1)")

    assert has_complete_formulas(complete, 3587)  # type: ignore[arg-type]
    assert not has_complete_formulas(partial, 3587)  # type: ignore[arg-type]
    assert not has_complete_formulas(missing_b, 3587)  # type: ignore[arg-type]
    assert not has_complete_formulas(static, 3587)  # type: ignore[arg-type]


def test_is_filled_values() -> None:
    assert is_filled(0)
    assert is_filled("94.7")
    assert not is_filled(None)
    assert not is_filled("")
    assert not is_filled("   ")
