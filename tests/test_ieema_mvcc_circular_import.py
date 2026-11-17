from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.oneoff.ieema_cables_circular import build_cables_rows
from sheet_data_automation.oneoff.ieema_mvcc_circular import parse_mvcc_text

SAMPLE = """
Cir. No. IEEMA(PVC)/MVCC/10/2026         October 2026
1. ALUMINIUM: (Al)   Rs.  3,44,733.00/MT   (-)  31,488.00
3.  Semiconducting conductor screening: (SC)      Rs.  3,80,103.00/MT   +   9,608.00
    XLPE Compound        Rs.  2,48,379.00/MT
"""


def test_parse_only_semiconducting_price() -> None:
    data = parse_mvcc_text(SAMPLE)
    assert data.month_start == dt.date(2026, 10, 1)
    assert data.prices == {"AD": 380103}
    rows = build_cables_rows(data)
    assert len(rows) == 31
    assert rows[dt.date(2026, 10, 31)] == {"AD": 380103}


def test_missing_price_raises() -> None:
    with pytest.raises(ParseError, match="not found"):
        parse_mvcc_text(SAMPLE.replace("Semiconducting conductor screening", "Other item"))


def test_real_pdf_when_present() -> None:
    from sheet_data_automation.common.pdftext import extract_text

    pdf = Path(__file__).resolve().parents[1] / "October 2026.pdf"
    if not pdf.is_file():
        pytest.skip("MVCC PDF not available")
    assert parse_mvcc_text(extract_text(pdf.read_bytes(), layout=True)).prices == {"AD": 380103}
