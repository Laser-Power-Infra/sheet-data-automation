from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    Locator,
    Page,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from ..common.browser import BrowserSession, dump_failure
from ..common.errors import ParseError, ScrapeError
from ..common.pdf_callback import PdfCallback, notify_pdf
from ..common.pdftext import extract_text, parse_price

LOGGER = logging.getLogger(__name__)

IE07_PATTERN = re.compile(r"(?i)\bALUMINIUM\s+INGOT\s+IE07\s+([\d,]+)")
WEF_PATTERN = re.compile(r"(?i)w\.e\.f\.?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})")

PRODUCT_SECTION = "div.product-section"

IngotScrapeError = ScrapeError
PriceParseError = ParseError


@dataclass(frozen=True)
class IngotPrice:
    price: int
    pdf_url: str
    wef_date: str | None


def parse_ie07_price(text: str) -> int:
    match = IE07_PATTERN.search(text)
    if not match:
        raise ParseError("IE07 row not found in the price circular")
    return parse_price(match.group(1))


def parse_wef_date(text: str) -> str | None:
    match = WEF_PATTERN.search(text)
    return match.group(1) if match else None


def _find_ingots_tile(page: Page) -> Locator | None:
    try:
        by_text = page.locator(PRODUCT_SECTION + " a").filter(
            has=page.locator('p:text-is("Ingots")')
        )
        if by_text.count() > 0:
            return by_text.first
        by_image = page.locator(PRODUCT_SECTION + ' a:has(img[data-src$="/ingot-nalco.jpg"])')
        if by_image.count() > 0:
            return by_image.first
    except PlaywrightError as exc:
        LOGGER.debug("Ingots tile lookup failed: %s", exc)
    return None


def fetch_ingot_price(
    page_url: str,
    session: BrowserSession,
    *,
    logs_dir: Path | None = None,
    on_pdf: PdfCallback | None = None,
) -> IngotPrice:
    page = session.new_page()
    try:
        LOGGER.info("Opening NALCO price page: %s", page_url)
        response = page.goto(page_url, wait_until="domcontentloaded")
        if response is not None and not response.ok:
            raise ScrapeError(f"NALCO page returned HTTP {response.status}")

        tile = _find_ingots_tile(page)
        if tile is None:
            raise ScrapeError("Ingots tile not found in the NALCO product section")

        tile.wait_for(state="visible", timeout=15000)
        tile.scroll_into_view_if_needed()
        download = session.click_pdf(page, tile, page_url, "NALCO Ingots tile", logs_dir)

        try:
            text = extract_text(download.data)
            price = parse_ie07_price(text)
            wef_date = parse_wef_date(text)
        except ParseError:
            notify_pdf(on_pdf, download.data, download.url, None)
            raise
        notify_pdf(on_pdf, download.data, download.url, wef_date)

        LOGGER.info(
            "NALCO IE07: %s (w.e.f %s) from %s",
            price,
            wef_date or "unknown",
            download.url,
        )
        return IngotPrice(price=price, pdf_url=download.url, wef_date=wef_date)
    except ParseError:
        dump_failure(page, logs_dir, "NALCO Ingots")
        raise
    except PlaywrightTimeoutError as exc:
        dump_failure(page, logs_dir, "NALCO Ingots")
        raise ScrapeError(f"NALCO page timed out: {exc}") from exc
    except ScrapeError:
        dump_failure(page, logs_dir, "NALCO Ingots")
        raise
    except PlaywrightError as exc:
        dump_failure(page, logs_dir, "NALCO Ingots")
        raise ScrapeError(f"NALCO page failed: {exc}") from exc
    finally:
        try:
            page.close()
        except PlaywrightError:
            pass
