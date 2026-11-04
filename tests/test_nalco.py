from __future__ import annotations

import pytest

from sheet_data_automation.cacmai_conductors.nalco import (
    PriceParseError,
    parse_ie07_price,
    parse_wef_date,
)

SAMPLE_TEXT = """
           NATIONAL ALUMINIUM COMPANY LIMITED
                  NALCO BHAWAN P/1 NAYAPALLI
                     BHUBANESWAR - 751013
PRICE CIRCULAR OF ALUMINIUM METAL FOR SALE IN DOMESTIC MARKET
Sl.no. Description Product Code
Basic Price Ex-
Works w.e.f
16.10.2026
1 ALUMINIUM ALLOY INGOT IA10 338050
10 ALUMINIUM INGOT IC20 335450
11 ALUMINIUM INGOT IE07 335750
12 ALUMINIUM INGOT IE10 335700
(Prices in Rupees Per MT)
"""


def test_parses_ie07_price() -> None:
    assert parse_ie07_price(SAMPLE_TEXT) == 335750


def test_parses_ie07_price_with_commas() -> None:
    assert parse_ie07_price("ALUMINIUM INGOT IE07 3,35,750") == 335750


def test_parses_wef_date() -> None:
    assert parse_wef_date(SAMPLE_TEXT) == "16.10.2026"


def test_wef_date_missing_returns_none() -> None:
    assert parse_wef_date("no date here") is None


def test_missing_ie07_raises() -> None:
    with pytest.raises(PriceParseError):
        parse_ie07_price("ALUMINIUM INGOT IE10 335700")


def test_alloy_ingot_is_not_ie07() -> None:
    with pytest.raises(PriceParseError):
        parse_ie07_price("ALUMINIUM ALLOY INGOT IA10 338050")
