from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.oneoff.ieema_circular import (
    build_ieema_rows,
    parse_ieema_pdf,
    parse_ieema_text,
)

SAMPLE = """
  01-Oct-26     $3,120.00     $266.5     3,53,376
  02-Oct-26     $3,109.50     $266.5     3,52,280
  05-Oct-26     $3,107.00     $264.0     3,52,938
   Average      $3,061.11     $261.43    3,44,733
HIGH TENSILE GALVANISED STEEL WIRE (FE)    Prices exclusive of all duties
1.57 mm     Rs. Laser Power & Infra Ltd  1,14,813     /-MT    $  1,198.47     /-MT
2.11 to 2.21 mm    Rs.     1,03,313     /-MT    $  1,078.42     /-MT
2.54 to 2.59 mm    Rs.     98,688     /-MT    $  1,030.15     /-MT
3.00 to 4.09 mm    Rs.     96,063     /-MT    $  1,002.75     /-MT
3.53 mm (PGCIL)    Rs.     96,646     /-MT    $  1,008.83     /-MT
"""


def test_parse_and_build_rows() -> None:
    data = parse_ieema_text(SAMPLE)
    assert data.average_inr == 344733
    assert data.steel == (114813, 103313, 98688, 96063, 96646)
    rows = build_ieema_rows(data)

    assert len(rows) == 5
    assert rows[dt.date(2026, 10, 1)] == {
        "E": 3120.0, "F": 266.5, "C": 353376, "G": 344733,
        "H": 114813, "I": 103313, "J": 98688, "K": 96063, "L": 96646,
    }
    assert rows[dt.date(2026, 10, 3)] == rows[dt.date(2026, 10, 2)]
    assert rows[dt.date(2026, 10, 4)] == rows[dt.date(2026, 10, 2)]


def test_missing_steel_raises() -> None:
    with pytest.raises(ParseError, match="steel wire"):
        parse_ieema_text(SAMPLE.replace("3.53 mm (PGCIL)    Rs.", "3.53 mm (PGCIL)"))


def test_real_pdf_when_present() -> None:
    pdf = Path(__file__).resolve().parents[1] / "01-10-2026.pdf"
    if not pdf.is_file():
        pytest.skip("01-10-2026.pdf not available")
    data = parse_ieema_pdf(pdf)
    rows = build_ieema_rows(data)

    assert len(data.dates) == 22
    assert len(rows) == 30
    assert rows[dt.date(2026, 10, 1)]["C"] == 353376
    assert rows[dt.date(2026, 10, 1)]["E"] == 3120.0
    assert rows[dt.date(2026, 10, 1)]["H"] == 114813
    assert rows[dt.date(2026, 10, 3)] == rows[dt.date(2026, 10, 2)]
    assert dt.date(2026, 10, 31) not in rows
