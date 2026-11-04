from __future__ import annotations

import os
from dataclasses import dataclass

from ..common.config import validate_cell, validate_column

DEFAULT_TAB_NAME = "CACMAI CONDUCTORS"


@dataclass(frozen=True)
class CacmaiConfig:
    tab_name: str
    link_cell: str
    product_code: str
    date_column: str
    price_column: str
    balco_link_cell: str
    hindalco_link_cell: str
    balco_cg_column: str
    hindalco_column: str
    vedanta_column: str


def load_cacmai_config() -> CacmaiConfig:
    return CacmaiConfig(
        tab_name=os.getenv("TAB_NAME", DEFAULT_TAB_NAME).strip(),
        link_cell=validate_cell(os.getenv("LINK_CELL", "T1"), "LINK_CELL"),
        product_code=os.getenv("PRODUCT_CODE", "IE07").strip(),
        date_column=validate_column(os.getenv("DATE_COLUMN", "A"), "DATE_COLUMN"),
        price_column=validate_column(os.getenv("PRICE_COLUMN", "T"), "PRICE_COLUMN"),
        balco_link_cell=validate_cell(os.getenv("BALCO_LINK_CELL", "U1"), "BALCO_LINK_CELL"),
        hindalco_link_cell=validate_cell(
            os.getenv("HINDALCO_LINK_CELL", "V1"), "HINDALCO_LINK_CELL"
        ),
        balco_cg_column=validate_column(
            os.getenv("BALCO_CG_COLUMN", "U"), "BALCO_CG_COLUMN"
        ),
        hindalco_column=validate_column(os.getenv("HINDALCO_COLUMN", "V"), "HINDALCO_COLUMN"),
        vedanta_column=validate_column(os.getenv("VEDANTA_COLUMN", "W"), "VEDANTA_COLUMN"),
    )
