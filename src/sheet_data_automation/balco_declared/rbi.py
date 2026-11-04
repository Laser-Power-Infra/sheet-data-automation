from __future__ import annotations

import datetime as dt
import logging
import math
import re
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
)

from ..common.browser import BrowserSession, dump_failure
from ..common.errors import ParseError, ScrapeError

LOGGER = logging.getLogger(__name__)

NO_RATE_TEXT = "No Reference Rate Found."
USD_HEADER = "USD (INR / 1 USD)"
RATE_PATTERN = r"([0-9]+(?:\.[0-9]+)?)"


def format_rbi_date(value: dt.date) -> str:
    return value.strftime("%d/%m/%Y")


def parse_rbi_rate(text: str, date_text: str) -> float | None:
    if NO_RATE_TEXT in text:
        return None
    match = re.search(re.escape(date_text) + r"\s+" + RATE_PATTERN, text)
    if not match:
        return None
    rate = float(match.group(1))
    if not math.isfinite(rate) or rate <= 0:
        raise ParseError(f"Invalid RBI rate: {rate}")
    return rate


def lookup_usd_rate(
    page_url: str,
    lookup_date: dt.date,
    session: BrowserSession,
    *,
    logs_dir: Path | None = None,
    timeout_ms: int = 60000,
) -> float | None:
    date_text = format_rbi_date(lookup_date)
    page = session.new_page()
    try:
        for attempt in (1, 2):
            try:
                LOGGER.info("Opening RBI archive: %s", page_url)
                page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.evaluate(
                    """
                    (dateText) => {
                        const from = document.getElementById('txtFromDate');
                        const to = document.getElementById('txtToDate');
                        from.value = dateText;
                        to.value = dateText;
                        from.dispatchEvent(new Event('input', { bubbles: true }));
                        to.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    """,
                    date_text,
                )
                page.check("#chkUSD")
                with page.expect_navigation(timeout=timeout_ms):
                    page.click("#btnSubmit")
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

                body = page.inner_text("body")
                if NO_RATE_TEXT in body:
                    LOGGER.info("RBI has no USD rate for %s", date_text)
                    return None

                table = page.locator("table").filter(has_text=USD_HEADER).first
                if table.count() == 0:
                    raise ParseError("RBI USD result table not found")

                rate = parse_rbi_rate(table.inner_text(), date_text)
                if rate is None:
                    LOGGER.warning("RBI result did not contain a rate for %s", date_text)
                    return None

                LOGGER.info("RBI USD rate for %s: %s", date_text, rate)
                return rate
            except (PlaywrightError, ScrapeError, ParseError) as exc:
                LOGGER.warning("RBI lookup attempt %s failed: %s", attempt, exc)
                if attempt == 2:
                    dump_failure(page, logs_dir, "RBI USD rate")
                    raise ScrapeError(f"RBI lookup failed for {date_text}: {exc}") from exc
                page.wait_for_timeout(1000)
        return None
    finally:
        try:
            page.close()
        except PlaywrightError:
            pass
