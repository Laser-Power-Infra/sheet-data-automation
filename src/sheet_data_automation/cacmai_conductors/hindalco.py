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

CG995_PATTERN = re.compile(
    r"CG\s+Grade\s+Ingot\s*&\s*Sow\s+99\.5%\s*\(min\)\s*purity\s+([\d,]+)",
    re.IGNORECASE,
)
AS_ON_PATTERN = re.compile(r"as on\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)

LIST_ITEM = "ul.left-pdf-list-ul li a.pdf-list-in"


@dataclass(frozen=True)
class HindalcoPrice:
    price: int
    pdf_url: str
    as_on: str | None


def parse_hindalco_price(text: str) -> int:
    match = CG995_PATTERN.search(text)
    if not match:
        raise ParseError("Hindalco 'CG Grade Ingot & Sow 99.5% (min) purity' row not found")
    return parse_price(match.group(1))


def parse_as_on(text: str) -> str | None:
    match = AS_ON_PATTERN.search(text)
    return match.group(1) if match else None


def fetch_hindalco_price(
    page_url: str,
    session: BrowserSession,
    *,
    logs_dir: Path | None = None,
    on_pdf: PdfCallback | None = None,
) -> HindalcoPrice:
    page = session.new_page()
    try:
        LOGGER.info("Opening Hindalco price page: %s", page_url)
        response = page.goto(page_url, wait_until="domcontentloaded")
        if response is not None and not response.ok:
            raise ScrapeError(f"Hindalco page returned HTTP {response.status}")

        link = page.locator(LIST_ITEM).first
        link.wait_for(state="visible", timeout=15000)
        link.scroll_into_view_if_needed()

        label = link.inner_text().strip().replace("\n", " ")
        LOGGER.info("Hindalco first ready reckoner: %s", label)

        download = session.click_pdf(
            page, link, page_url, "Hindalco first ready reckoner", logs_dir
        )
        try:
            text = extract_text(download.data, layout=True)
            price = parse_hindalco_price(text)
            as_on = parse_as_on(label)
        except ParseError:
            notify_pdf(on_pdf, download.data, download.url, None)
            raise
        notify_pdf(on_pdf, download.data, download.url, as_on)

        LOGGER.info(
            "Hindalco CG 99.5%%: %s (as on %s) from %s",
            price,
            as_on or "unknown",
            download.url,
        )
        return HindalcoPrice(price=price, pdf_url=download.url, as_on=as_on)
    except ParseError:
        dump_failure(page, logs_dir, "Hindalco first ready reckoner")
        raise
    except PlaywrightTimeoutError as exc:
        dump_failure(page, logs_dir, "Hindalco first ready reckoner")
        raise ScrapeError(f"Hindalco page timed out: {exc}") from exc
    except ScrapeError:
        dump_failure(page, logs_dir, "Hindalco first ready reckoner")
        raise
    except PlaywrightError as exc:
        dump_failure(page, logs_dir, "Hindalco first ready reckoner")
        raise ScrapeError(f"Hindalco page failed: {exc}") from exc
    finally:
        try:
            page.close()
        except PlaywrightError:
            pass
