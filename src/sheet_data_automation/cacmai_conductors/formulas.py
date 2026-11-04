from __future__ import annotations

import logging
from typing import Any

import gspread

from ..common.google import FIRST_DATA_ROW, column_index, sheet_op

LOGGER = logging.getLogger(__name__)

FORMULA_COLUMNS = ("X", "Y", "Z", "AA")
B_FORMULA_COLUMN = "B"
FORMULA_SOURCE_SEARCH_LIMIT = 20


def is_formula_values(cells: list[Any]) -> bool:
    if len(cells) != len(FORMULA_COLUMNS):
        return False
    return all(isinstance(cell, str) and cell.startswith("=") for cell in cells)


def _copy_request(
    sheet_id: int,
    source_row: int,
    target_row: int,
    start_column: int,
    end_column: int,
) -> dict[str, Any]:
    return {
        "copyPaste": {
            "source": {
                "sheetId": sheet_id,
                "startRowIndex": source_row - 1,
                "endRowIndex": source_row,
                "startColumnIndex": start_column,
                "endColumnIndex": end_column,
            },
            "destination": {
                "sheetId": sheet_id,
                "startRowIndex": target_row - 1,
                "endRowIndex": target_row,
                "startColumnIndex": start_column,
                "endColumnIndex": end_column,
            },
            "pasteType": "PASTE_NORMAL",
            "pasteOrientation": "NORMAL",
        }
    }


def build_formula_fill_request(
    sheet_id: int,
    source_row: int,
    target_row: int,
) -> dict[str, Any]:
    start_column = column_index(FORMULA_COLUMNS[0]) - 1
    end_column = column_index(FORMULA_COLUMNS[-1])
    b_column = column_index(B_FORMULA_COLUMN) - 1
    return {
        "requests": [
            _copy_request(sheet_id, source_row, target_row, b_column, b_column + 1),
            _copy_request(sheet_id, source_row, target_row, start_column, end_column),
        ]
    }


@sheet_op
def find_formula_source_row(
    worksheet: gspread.Worksheet,
    target_row: int,
    *,
    first_row: int = FIRST_DATA_ROW,
) -> int | None:
    lowest_row = max(first_row, target_row - FORMULA_SOURCE_SEARCH_LIMIT)
    if target_row <= lowest_row:
        return None

    b_rows = worksheet.get(
        f"{B_FORMULA_COLUMN}{lowest_row}:{B_FORMULA_COLUMN}{target_row - 1}",
        value_render_option="FORMULA",
    )
    xaa_rows = worksheet.get(
        f"{FORMULA_COLUMNS[0]}{lowest_row}:{FORMULA_COLUMNS[-1]}{target_row - 1}",
        value_render_option="FORMULA",
    )
    for offset in range(len(xaa_rows) - 1, -1, -1):
        b_cells = b_rows[offset] if offset < len(b_rows) else []
        b_formula = b_cells[0] if b_cells else ""
        if (
            isinstance(b_formula, str)
            and b_formula.startswith("=")
            and is_formula_values(xaa_rows[offset])
        ):
            return lowest_row + offset
    return None


@sheet_op
def read_formula_row(worksheet: gspread.Worksheet, row: int) -> dict[str, str]:
    b_value = worksheet.acell(f"{B_FORMULA_COLUMN}{row}", value_render_option="FORMULA").value
    range_name = f"{FORMULA_COLUMNS[0]}{row}:{FORMULA_COLUMNS[-1]}{row}"
    values = worksheet.get(range_name, value_render_option="FORMULA")
    cells = values[0] if values else []
    formulas = {
        column: str(cells[index]) if index < len(cells) else ""
        for index, column in enumerate(FORMULA_COLUMNS)
    }
    formulas[B_FORMULA_COLUMN] = str(b_value) if b_value is not None else ""
    return formulas


def has_complete_formulas(worksheet: gspread.Worksheet, row: int) -> bool:
    formulas = read_formula_row(worksheet, row)
    return formulas[B_FORMULA_COLUMN].startswith("=") and is_formula_values(
        [formulas[column] for column in FORMULA_COLUMNS]
    )


@sheet_op
def fill_down_formulas(
    worksheet: gspread.Worksheet,
    target_row: int,
    *,
    first_row: int = FIRST_DATA_ROW,
) -> dict[str, str]:
    source_row = find_formula_source_row(worksheet, target_row, first_row=first_row)
    if source_row is None:
        raise RuntimeError(
            f"No previous row with formulas in {FORMULA_COLUMNS[0]}:{FORMULA_COLUMNS[-1]} was found"
        )

    body = build_formula_fill_request(worksheet.id, source_row, target_row)
    worksheet.spreadsheet.batch_update(body)

    formulas = read_formula_row(worksheet, target_row)
    if not (
        formulas[B_FORMULA_COLUMN].startswith("=")
        and is_formula_values([formulas[column] for column in FORMULA_COLUMNS])
    ):
        raise RuntimeError(
            f"Fill-down did not produce formulas in "
            f"{B_FORMULA_COLUMN}{target_row} or "
            f"{FORMULA_COLUMNS[0]}{target_row}:{FORMULA_COLUMNS[-1]}{target_row}"
        )

    LOGGER.info("Pulled formulas from row %s to row %s", source_row, target_row)
    for column, formula in formulas.items():
        LOGGER.info("  %s%s = %s", column, target_row, formula)
    return formulas

