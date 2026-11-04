from __future__ import annotations

import pytest

from sheet_data_automation.cacmai_conductors.hindalco import parse_as_on, parse_hindalco_price
from sheet_data_automation.common.errors import ParseError

SAMPLE_TEXT = """
Hindalco Industries Limited
Primary Aluminium Products' Price Ready Reckoner w.e.f. 15.10.2026

P0610 (99.85% min) /P1020/ EC Grade Ingot & Sow 99.7% (min) / Cast Bar  3,36,500
CG Grade Ingot & Sow 99.5% (min) purity 3,36,000
EC Grade Wire Rods, Dia 9.5 mm - Conductivity 61% min 3,45,250
"""


def test_parses_hindalco_cg995() -> None:
    assert parse_hindalco_price(SAMPLE_TEXT) == 336000


def test_missing_hindalco_row_raises() -> None:
    with pytest.raises(ParseError):
        parse_hindalco_price("EC Grade Wire Rods 3,45,250")


def test_parses_as_on_date() -> None:
    label = "Primary metal price Ready Reckoner as on 15.10.2026"
    assert parse_as_on(label) == "15.10.2026"
    assert parse_as_on("no date") is None
