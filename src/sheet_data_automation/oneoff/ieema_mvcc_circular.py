from __future__ import annotations

import datetime as dt
import re

from ..common.errors import ParseError
from .ieema_cables_circular import MONTH, CablesData

TARGET_COLUMNS = ("AD",)  # Semiconducting conductor screening (SC) on IEEMA CABLES
SC_LINE = re.compile(r"Semiconducting conductor screening", re.IGNORECASE)
PRICE = re.compile(r"Rs\.\s*([\d,]+)(?:\.\d+)?\s*/\s*MT")


def parse_mvcc_text(text: str) -> CablesData:
    month = MONTH.search(text)
    if not month:
        raise ParseError("Month not found in the MVCC circular")
    month_start = dt.datetime.strptime(f"{month.group(1)} {month.group(2)}", "%B %Y").date()

    found = [
        int(price.group(1).replace(",", ""))
        for line in text.splitlines()
        if SC_LINE.search(line) and (price := PRICE.search(line))
    ]
    if not found:
        raise ParseError("MVCC circular: Semiconducting conductor screening price not found")
    if len(found) > 1:
        raise ParseError("MVCC circular: more than one Semiconducting screening price found")
    return CablesData(month_start=month_start, prices={"AD": found[0]})
