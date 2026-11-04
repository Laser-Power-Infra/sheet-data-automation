from __future__ import annotations

import datetime as dt

import pytest

from sheet_data_automation.balco_declared.lme import (
    LmeSource,
    extract_lme_url,
    parse_lme_offer,
    select_official_payload,
)
from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.common.values import same_number

OFFICIAL_PAYLOAD = {
    "DateOfData": "2026-10-22T00:00:00",
    "Labels": ["21/10/2026", "22/10/2026"],
    "Datasets": [
        {"RowTitle": "Cash", "Label": "Bid", "Data": ["3030.00", "3032.50"]},
        {"RowTitle": "Cash", "Label": "Offer", "Data": ["3031.00", "3033.00"]},
        {"RowTitle": "3-month", "Label": "Offer", "Data": ["3007.00", "3008.00"]},
    ],
}

CLOSING_PAYLOAD = {
    "DateOfData": "2026-10-22T00:00:00",
    "Labels": ["21/10/2026", "22/10/2026"],
    "Datasets": [
        {"RowTitle": "3-month", "Label": "Price", "Data": ["3009.00", "3010.00"]},
    ],
}

SOURCE = LmeSource(
    metal="Aluminium",
    link_cell="C1",
    column="C",
    datasource_id="dddbc815-1a81-4f35-beed-6a193f4c946a",
)


def test_extract_lme_url_from_cell_with_credentials() -> None:
    value = (
        "C ID: user@example.com; pwd: secret\n"
        "https://www.lme.com/en/Metals/Non-ferrous/LME-Aluminium#Price+graphs"
    )
    assert extract_lme_url(value) == "https://www.lme.com/en/Metals/Non-ferrous/LME-Aluminium"


def test_extract_lme_url_before_trailing_credentials() -> None:
    value = (
        "https://www.lme.com/en/Metals/Non-ferrous/LME-Copper#Trading+day+summary "
        "ID: user@example.com; pwd: secret\n"
    )
    assert extract_lme_url(value) == "https://www.lme.com/en/Metals/Non-ferrous/LME-Copper"


def test_select_official_payload_ignores_closing_payload() -> None:
    assert select_official_payload([CLOSING_PAYLOAD, OFFICIAL_PAYLOAD]) is OFFICIAL_PAYLOAD
    assert select_official_payload([CLOSING_PAYLOAD]) is None


def test_parse_lme_offer_uses_latest_cash_offer() -> None:
    quote = parse_lme_offer(OFFICIAL_PAYLOAD, SOURCE)
    assert quote is not None
    assert quote.value == 3033.0
    assert quote.data_date == dt.date(2026, 10, 22)
    assert quote.column == "C"


def test_parse_lme_offer_missing_offer_returns_none() -> None:
    assert parse_lme_offer(CLOSING_PAYLOAD, SOURCE) is None


def test_parse_lme_offer_invalid_date_raises() -> None:
    payload = {
        "Labels": ["not-a-date"],
        "Datasets": [{"RowTitle": "Cash", "Label": "Offer", "Data": ["3033"]}],
    }
    with pytest.raises(ParseError):
        parse_lme_offer(payload, SOURCE)


def test_parse_lme_offer_zero_raises() -> None:
    payload = {
        "Labels": ["22/10/2026"],
        "Datasets": [{"RowTitle": "Cash", "Label": "Offer", "Data": ["0"]}],
    }
    with pytest.raises(ParseError):
        parse_lme_offer(payload, SOURCE)


def test_parse_lme_offer_non_finite_raises() -> None:
    payload = {
        "Labels": ["22/10/2026"],
        "Datasets": [{"RowTitle": "Cash", "Label": "Offer", "Data": ["NaN"]}],
    }
    with pytest.raises(ParseError):
        parse_lme_offer(payload, SOURCE)


def test_same_number() -> None:
    assert same_number(3033, 3033.0)
    assert same_number("3033.00", 3033.0)
    assert not same_number(None, 3033.0)
    assert not same_number("", 3033.0)
    assert not same_number(3031, 3033.0)
