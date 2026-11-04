from __future__ import annotations

import pytest

from sheet_data_automation.cacmai_conductors.balco import parse_balco_prices
from sheet_data_automation.common.errors import ParseError

SAMPLE_TEXT = """
W.E.F.                        22.10.2026

ALUMINIUM PRIMARY METAL - BHARAT ALUMINIUM CO. LTD & VEDANTA LTD.

BASIC PRICE - INGOTS
PRODUCT                                                   INR/MT
P1020 / EC High purity above 99.7%                       340250
EC 99.6% / EC 99.5% / CG 99.5%                           340000
CG 99 %                                                  339250
AlSi T Ingot                                             352250
"""


def test_parses_balco_cg99_and_combined_row() -> None:
    cg99, ec_cg, wef = parse_balco_prices(SAMPLE_TEXT)
    assert cg99 == 339250
    assert ec_cg == 340000
    assert wef == "22.10.2026"


def test_combined_row_only_does_not_satisfy_cg99() -> None:
    text = "EC 99.6% / EC 99.5% / CG 99.5% 340000"
    with pytest.raises(ParseError, match="CG 99"):
        parse_balco_prices(text)


def test_missing_combined_row_raises() -> None:
    text = "CG 99 % 339250"
    with pytest.raises(ParseError, match="EC 99.6"):
        parse_balco_prices(text)
