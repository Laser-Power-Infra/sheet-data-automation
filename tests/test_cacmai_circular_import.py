from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from sheet_data_automation.common.errors import ParseError
from sheet_data_automation.oneoff.cacmai_circular import (
    build_circular_rows,
    parse_circular_pdf,
    parse_circular_text,
)

SAMPLE_TEXT = """
A. Aluminium /Average Basic Price Index per M.T. in Rupees.

 DATE                              E.C.INGOTS/ALUMINI            E.C.WIRE ROD                 ALLOY     WIRE ROD
                                   UM HOT METAL.
01.10.2026                       387650                        395663                        406200
02.10.2026                       381713                        389725                        398075
07.10.2026                       383400                        391413                        400450
NOTE:   GST as applicable is extra.
a. INGOTS/ALUMINIUM HOT METAL.
Effective date      NALCO               BALCO               HINDALCO           VEDANTA             AVERAGE
01.10.2026         378000             397200              378000              397400              387650
02.10.2026         378000             389700              369250              389900              381713
07.10.2026         378000             391700              372000              391900              383400

b. RODS.
 Effective date      NALCO                BALCO                HINDALCO             VEDANTA              AVERAGE
 01.10.2026         378950               406600               391000               406100              395663
 02.10.2026         378950               399100               382250               398600              389725
 07.10.2026         378950               401100               385000               400600              391413

C.ALLOY RODS.
 Effective date                 BALCO                           HINDALCO                       AVERAGE
01.10.2026                      413400                         399000                          406200
02.10.2026                      405900                         390250                          398075
07.10.2026                      407900                         393000                          400450

For Cable and Conductor Manufacturers Association of India
"""


def test_parse_sections() -> None:
    data = parse_circular_text(SAMPLE_TEXT)
    assert data.dates == [dt.date(2026, 10, 1), dt.date(2026, 10, 2), dt.date(2026, 10, 7)]
    assert data.ec[dt.date(2026, 10, 1)] == (387650, 395663, 406200)
    assert data.ingots[dt.date(2026, 10, 1)] == (378000, 397200, 378000, 397400, 387650)
    assert data.rods[dt.date(2026, 10, 1)] == (378950, 406600, 391000, 406100, 395663)
    assert data.alloy_rods[dt.date(2026, 10, 1)] == (413400, 399000, 406200)


def test_build_rows_maps_columns_and_carries_forward() -> None:
    rows = build_circular_rows(parse_circular_text(SAMPLE_TEXT))

    assert len(rows) == 7
    assert rows[dt.date(2026, 10, 3)] == rows[dt.date(2026, 10, 2)]
    assert rows[dt.date(2026, 10, 6)] == rows[dt.date(2026, 10, 2)]
    assert rows[dt.date(2026, 10, 7)]["C"] == 383400
    assert rows[dt.date(2026, 10, 1)]["O"] == 378000
    assert rows[dt.date(2026, 10, 1)]["S"] == 387650
    assert rows[dt.date(2026, 10, 1)]["AM"] == 378950
    assert rows[dt.date(2026, 10, 1)]["AQ"] == 395663
    assert rows[dt.date(2026, 10, 1)]["AS"] == 413400
    assert rows[dt.date(2026, 10, 1)]["AT"] == 399000
    assert rows[dt.date(2026, 10, 1)]["AV"] == 406200
    assert "AR" not in rows[dt.date(2026, 10, 1)]
    assert "AU" not in rows[dt.date(2026, 10, 1)]


def test_top_table_must_match_section_averages() -> None:
    broken = SAMPLE_TEXT.replace("01.10.2026                       387650", "01.10.2026 999999")
    with pytest.raises(ParseError, match="do not match section averages"):
        parse_circular_text(broken)


def test_missing_section_raises() -> None:
    with pytest.raises(ParseError, match="Section header not found"):
        parse_circular_text(SAMPLE_TEXT.replace("a. INGOTS/ALUMINIUM HOT METAL.", "a. INGOTS"))


def test_real_pdf_when_present() -> None:
    pdf = Path(__file__).resolve().parents[1] / "Doc13L-108.pdf"
    if not pdf.is_file():
        pytest.skip("Doc13L-108.pdf not available")
    data = parse_circular_pdf(pdf)
    rows = build_circular_rows(data)

    assert len(data.dates) == 9
    assert data.dates[0] == dt.date(2026, 10, 1)
    assert data.dates[-1] == dt.date(2026, 10, 16)
    assert len(rows) == 16
    assert rows[dt.date(2026, 10, 3)] == rows[dt.date(2026, 10, 2)]
    assert rows[dt.date(2026, 10, 12)] == rows[dt.date(2026, 10, 9)]
    assert dt.date(2026, 10, 17) not in rows
