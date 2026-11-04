from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from ..common.browser import BrowserSession, dump_failure
from ..common.errors import ParseError, ScrapeError
from ..common.pdf_callback import PdfCallback, notify_pdf
from ..common.pdftext import extract_text, parse_price

LOGGER = logging.getLogger(__name__)

CG99_PATTERN = re.compile(r"(?m)^\s*CG 99 %\s+([\d,]+)")
EC_CG_PATTERN = re.compile(r"(?m)^\s*EC 99\.6%\s*/\s*EC 99\.5%\s*/\s*CG 99\.5%\s+([\d,]+)")
WEF_PATTERN = re.compile(r"(?i)W\.E\.F\.\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})")

WRAPPER = "div.financial-box-wrapper.n-price-box-wrapper"


@dataclass(frozen=True)
class BalcoPrices:
    cg99: int
    ec_cg: int
    pdf_url: str
    wef_date: str | None


def parse_balco_prices(text: str) -> tuple[int, int, str | None]:
    cg99_match = CG99_PATTERN.search(text)
    if not cg99_match:
        raise ParseError("BALCO 'CG 99 %' row not found")
    ec_cg_match = EC_CG_PATTERN.search(text)
    if not ec_cg_match:
        raise ParseError("BALCO 'EC 99.6% / EC 99.5% / CG 99.5%' row not found")

    wef_match = WEF_PATTERN.search(text)
    wef_date = wef_match.group(1) if wef_match else None
    return (
        parse_price(cg99_match.group(1)),
        parse_price(ec_cg_match.group(1)),
        wef_date,
    )


def fetch_balco_prices(
    page_url: str,
    session: BrowserSession,
    *,
    logs_dir: Path | None = None,
    on_pdf: PdfCallback | None = None,
) -> BalcoPrices:
    page = session.new_page()
    try:
        LOGGER.info("Opening BALCO price page: %s", page_url)
        response = page.goto(page_url, wait_until="domcontentloaded")
        if response is not None and not response.ok:
            raise ScrapeError(f"BALCO page returned HTTP {response.status}")

        card = page.locator(WRAPPER + " .f-box").first
        link = card.locator("a:has(h6.f-box-title)").first
        if link.count() == 0:
            link = card.locator("a[href$='.pdf']").first

        link.wait_for(state="visible", timeout=15000)
        link.scroll_into_view_if_needed()
        title = link.inner_text().strip().replace("\n", " ")
        LOGGER.info("BALCO first circular: %s", title)

        download = session.click_pdf(page, link, page_url, "BALCO first circular", logs_dir)
        try:
            text = extract_text(download.data, layout=True)
            cg99, ec_cg, wef_date = parse_balco_prices(text)
        except ParseError:
            notify_pdf(on_pdf, download.data, download.url, None)
            raise
        notify_pdf(on_pdf, download.data, download.url, wef_date)

        LOGGER.info(
            "BALCO CG 99%%: %s | EC/CG combined (Vedanta): %s | w.e.f %s | %s",
            cg99,
            ec_cg,
            wef_date or "unknown",
            download.url,
        )
        return BalcoPrices(
            cg99=cg99,
            ec_cg=ec_cg,
            pdf_url=download.url,
            wef_date=wef_date,
        )
    except ParseError:
        dump_failure(page, logs_dir, "BALCO first circular")
        raise
    except PlaywrightTimeoutError as exc:
        dump_failure(page, logs_dir, "BALCO first circular")
        raise ScrapeError(f"BALCO page timed out: {exc}") from exc
    except ScrapeError:
        dump_failure(page, logs_dir, "BALCO first circular")
        raise
    except PlaywrightError as exc:
        dump_failure(page, logs_dir, "BALCO first circular")
        raise ScrapeError(f"BALCO page failed: {exc}") from exc
    finally:
        try:
            page.close()
        except PlaywrightError:
            pass
