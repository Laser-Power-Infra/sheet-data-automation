from __future__ import annotations

import os
from dataclasses import dataclass

from ..common.config import int_env, validate_cell, validate_column

DEFAULT_GID = 365981478


@dataclass(frozen=True)
class BalcoDeclaredConfig:
    gid: int
    date_column: str
    rate_column: str
    link_cell: str
    lme_aluminium_link_cell: str
    lme_copper_link_cell: str
    lme_zinc_link_cell: str
    lme_aluminium_column: str
    lme_copper_column: str
    lme_zinc_column: str


def load_balco_declared_config() -> BalcoDeclaredConfig:
    return BalcoDeclaredConfig(
        gid=int_env(os.getenv("BALCO_DECLARED_GID", str(DEFAULT_GID)), "BALCO_DECLARED_GID"),
        date_column=validate_column(
            os.getenv("BALCO_DECLARED_DATE_COLUMN", "A"), "BALCO_DECLARED_DATE_COLUMN"
        ),
        rate_column=validate_column(
            os.getenv("BALCO_DECLARED_RATE_COLUMN", "E"), "BALCO_DECLARED_RATE_COLUMN"
        ),
        link_cell=validate_cell(
            os.getenv("BALCO_DECLARED_LINK_CELL", "E1"), "BALCO_DECLARED_LINK_CELL"
        ),
        lme_aluminium_link_cell=validate_cell(
            os.getenv("BALCO_DECLARED_ALUMINIUM_LINK_CELL", "C1"),
            "BALCO_DECLARED_ALUMINIUM_LINK_CELL",
        ),
        lme_copper_link_cell=validate_cell(
            os.getenv("BALCO_DECLARED_COPPER_LINK_CELL", "R1"),
            "BALCO_DECLARED_COPPER_LINK_CELL",
        ),
        lme_zinc_link_cell=validate_cell(
            os.getenv("BALCO_DECLARED_ZINC_LINK_CELL", "X1"),
            "BALCO_DECLARED_ZINC_LINK_CELL",
        ),
        lme_aluminium_column=validate_column(
            os.getenv("BALCO_DECLARED_ALUMINIUM_COLUMN", "C"),
            "BALCO_DECLARED_ALUMINIUM_COLUMN",
        ),
        lme_copper_column=validate_column(
            os.getenv("BALCO_DECLARED_COPPER_COLUMN", "R"),
            "BALCO_DECLARED_COPPER_COLUMN",
        ),
        lme_zinc_column=validate_column(
            os.getenv("BALCO_DECLARED_ZINC_COLUMN", "X"),
            "BALCO_DECLARED_ZINC_COLUMN",
        ),
    )
