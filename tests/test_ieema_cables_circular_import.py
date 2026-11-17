from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.oneoff.ieema_cables_circular import (
    TARGET_COLUMNS,
    build_cables_rows,
    parse_cables_pdf,
    parse_cables_text,
)

SAMPLE = """
Cir. No.: IEEMA(PVC)CABLE (R-1)/10/2026        October 2026
1.  LME ALUMINIUM : (Al)
    LME Average Settlement Price including Premium        Rs.   3,44,733 /MT   (-)   31,488.00
2.  COPPER : (Cu) Price of copper wire rodFor the sole use of   Rs.  14,72,961/MT  +  3,448.00
    COPPER : (Cu) copper wire rod 19.6 mm #     Rs.   14,90,771/MT    +   5,743.00
3.  Price of Pig Lead (99.97%)      Rs.   2,15,200 /MT   +   600.00
4.  PVC COMPOUND : (PVC)Laser Power & Infra Ltd
    PVC             Rs.   1,96,375 /MT   +   7,000.00
    HR PVC          Rs.   1,97,375 /MT   +   7,000.00
    For LV Cable    Rs.   1,91,261 /MT
    For MV Cable    Rs.   2,48,379 /MT
    For EHV Cable   Rs.   2,66,045 /MT
    Polythelene PE ST7    Rs.   2,07,750/MT
    Zero halogen low smoke (LSZH)    Rs.   1,84,000/MT
    a) Round 1.40 mm dia    Rs.   91,250/MT   NIL
    b) Round 1.60 mm dia    Rs.   90,750/MT   NIL
    c) Round 2.00 mm dia    Rs.   89,250/MT   NIL
    d) Round 2.50 mm dia    Rs.   87,250/MT   NIL
    e) Round 3.15 mm dia    Rs.   86,250/MT   NIL
    f) Round 4.00 mm dia    Rs.   86,250/MT   NIL
    g) Flat 4 mm x 0.8 mm   Rs.   92,250/MT   NIL
    a)    25 X 0.5 mm       Rs.   1,38,700 /MT   +   2,000.00
    b)    32 X 0.8 mm       Rs.   1,33,617 /MT   +   1,334.00
"""

EXPECTED = {
    "D": 344733, "F": 1472961, "H": 1490771, "J": 215200, "K": 196375, "L": 197375,
    "M": 191261, "AB": 248379, "W": 266045, "O": 207750, "AC": 184000,
    "P": 91250, "Q": 90750, "X": 89250, "Y": 87250, "Z": 86250, "AA": 86250, "R": 92250,
    "S": 138700, "T": 133617,
}


def test_parse_maps_all_columns() -> None:
    data = parse_cables_text(SAMPLE)
    assert data.month_start == dt.date(2026, 10, 1)
    assert data.prices == EXPECTED
    assert set(data.prices) == set(TARGET_COLUMNS)


def test_build_rows_covers_whole_month() -> None:
    rows = build_cables_rows(parse_cables_text(SAMPLE))
    assert len(rows) == 31
    assert rows[dt.date(2026, 10, 31)] == EXPECTED
    assert rows[dt.date(2026, 10, 1)] == rows[dt.date(2026, 10, 17)]


def test_missing_item_raises() -> None:
    with pytest.raises(ParseError, match="no price found"):
        parse_cables_text(SAMPLE.replace("Round 3.15 mm dia    Rs.", "Round 3.15 mm dia"))


def test_real_pdf_when_present() -> None:
    pdf = Path(__file__).resolve().parents[1] / "01-10-2026 (1).pdf"
    if not pdf.is_file():
        pytest.skip("cables PDF not available")
    assert parse_cables_pdf(pdf).prices == EXPECTED
