from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DragSheetConfig:
    name: str
    gid: int
    first_data_row: int
    columns: tuple[str, ...] | None = None
    exclude_columns: tuple[str, ...] = ("A",)
    spill_columns: tuple[str, ...] = ()
    fill_end_column: str = "AA"


SHEETS = (
    DragSheetConfig(
        name="IEEMA PROV MCX",
        gid=1984490678,
        first_data_row=3,
        columns=None,
        exclude_columns=("A",),
    ),
    DragSheetConfig(
        name="IEEMA CABLES",
        gid=0,
        first_data_row=5,
        columns=("B", "E", "G"),
    ),
    DragSheetConfig(
        name="IEEMA CONDUCTOR",
        gid=1178120759,
        first_data_row=5,
        columns=("B", "D"),
    ),
    DragSheetConfig(
        name="NALCO DECLARED",
        gid=1927552542,
        first_data_row=2,
        columns=("B", "C", "D", "E", "F", "G", "H"),
        spill_columns=("I",),
    ),
)
