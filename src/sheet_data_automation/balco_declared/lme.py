from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    Page,
)

from ..common.browser import BrowserSession, dump_failure
from ..common.errors import ParseError, ScrapeError
from .config import BalcoDeclaredConfig

LOGGER = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://[^\s]+")
OFFICIAL_DATASOURCE_IDS = {
    "Aluminium": "dddbc815-1a81-4f35-beed-6a193f4c946a",
    "Copper": "39fabad0-95ca-491b-a733-bcef31818b16",
    "Zinc": "1a1aca59-3032-4ea6-b22b-18b151514b84",
}
CHART_WAIT_SECONDS = 20


@dataclass(frozen=True)
class LmeSource:
    metal: str
    link_cell: str
    column: str
    datasource_id: str


@dataclass(frozen=True)
class LmeQuote:
    metal: str
    column: str
    value: float
    data_date: dt.date


def lme_sources(config: BalcoDeclaredConfig) -> list[LmeSource]:
    return [
        LmeSource(
            metal="Aluminium",
            link_cell=config.lme_aluminium_link_cell,
            column=config.lme_aluminium_column,
            datasource_id=OFFICIAL_DATASOURCE_IDS["Aluminium"],
        ),
        LmeSource(
            metal="Copper",
            link_cell=config.lme_copper_link_cell,
            column=config.lme_copper_column,
            datasource_id=OFFICIAL_DATASOURCE_IDS["Copper"],
        ),
        LmeSource(
            metal="Zinc",
            link_cell=config.lme_zinc_link_cell,
            column=config.lme_zinc_column,
            datasource_id=OFFICIAL_DATASOURCE_IDS["Zinc"],
        ),
    ]


def extract_lme_url(value: str) -> str:
    match = URL_PATTERN.search(value or "")
    if not match:
        raise ValueError(f"No URL found in cell value: {value!r}")
    return match.group(0).rstrip(").,;'\"").split("#")[0]


def select_official_payload(payloads: list[dict]) -> dict | None:
    candidates = []
    for payload in payloads:
        datasets = payload.get("Datasets") or []
        if any(
            dataset.get("RowTitle") == "Cash" and dataset.get("Label") == "Offer"
            for dataset in datasets
        ):
            candidates.append(payload)
    if not candidates:
        return None
    return max(candidates, key=lambda payload: str(payload.get("DateOfData") or ""))


def parse_lme_offer(payload: dict, source: LmeSource) -> LmeQuote | None:
    labels = payload.get("Labels") or []
    datasets = payload.get("Datasets") or []
    offer = next(
        (
            dataset
            for dataset in datasets
            if dataset.get("RowTitle") == "Cash" and dataset.get("Label") == "Offer"
        ),
        None,
    )
    if offer is None:
        return None

    values = offer.get("Data") or []
    if not labels or not values:
        return None

    raw_value = str(values[-1]).replace(",", "").strip()
    if not raw_value:
        return None
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ParseError(f"Invalid LME {source.metal} offer value: {values[-1]!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ParseError(f"Invalid LME {source.metal} offer value: {value}")

    label = str(labels[-1])
    try:
        data_date = dt.datetime.strptime(label, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ParseError(f"Invalid LME {source.metal} date label: {label!r}") from exc

    return LmeQuote(
        metal=source.metal,
        column=source.column,
        value=value,
        data_date=data_date,
    )


def _open_price_graphs(page: Page) -> None:
    button = page.get_by_role("button", name="Price graphs", exact=True)
    if button.count() == 0:
        button = page.locator("button", has_text="Price graphs")
    if button.count() == 0:
        raise ScrapeError("LME 'Price graphs' tab not found")
    button.first.scroll_into_view_if_needed()
    button.first.click()


def _wait_for_official_payload(page: Page, payloads: list[dict]) -> dict | None:
    deadline = time.monotonic() + CHART_WAIT_SECONDS
    while time.monotonic() < deadline:
        payload = select_official_payload(payloads)
        if payload is not None:
            return payload
        page.wait_for_timeout(500)
    return None


def _fetch_payload_via_page(page: Page, datasource_id: str) -> dict:
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=30)
    api_url = (
        "https://www.lme.com/api/trading-data/chart-data"
        f"?datasourceId={datasource_id}"
        f"&startDate={start_date.isoformat()}"
        f"&endDate={end_date.isoformat()}"
    )
    result = page.evaluate(
        """
        async (url) => {
            const response = await fetch(url);
            return { status: response.status, text: await response.text() };
        }
        """,
        api_url,
    )
    if result.get("status") != 200:
        raise ScrapeError(f"LME chart API returned HTTP {result.get('status')}")
    try:
        return json.loads(result["text"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise ScrapeError(f"Could not parse LME chart API response: {exc}") from exc


def fetch_quote(
    source: LmeSource,
    link_value: str,
    session: BrowserSession,
    *,
    logs_dir: Path | None = None,
) -> LmeQuote | None:
    page_url = extract_lme_url(link_value)
    page = session.new_page()
    payloads: list[dict] = []

    def on_response(response) -> None:
        if "chart-data" not in response.url:
            return
        try:
            payloads.append(response.json())
        except (PlaywrightError, ValueError):
            return

    page.on("response", on_response)

    try:
        for attempt in (1, 2):
            payloads.clear()
            try:
                LOGGER.info("Opening LME %s page: %s", source.metal, page_url)
                page.goto(page_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2000)
                _open_price_graphs(page)

                payload = _wait_for_official_payload(page, payloads)
                if payload is None:
                    LOGGER.info(
                        "No captured LME chart payload for %s; using API fallback",
                        source.metal,
                    )
                    payload = _fetch_payload_via_page(page, source.datasource_id)

                quote = parse_lme_offer(payload, source)
                if quote is None:
                    LOGGER.warning("LME %s has no Cash Offer value", source.metal)
                    return None
                LOGGER.info(
                    "LME %s Cash Offer: %s (data date %s)",
                    source.metal,
                    quote.value,
                    quote.data_date.isoformat(),
                )
                return quote
            except (PlaywrightError, ScrapeError, ParseError, ValueError) as exc:
                LOGGER.warning("LME %s attempt %s failed: %s", source.metal, attempt, exc)
                if attempt == 2:
                    dump_failure(page, logs_dir, f"LME {source.metal}")
                    raise ScrapeError(f"LME {source.metal} lookup failed: {exc}") from exc
                page.wait_for_timeout(1000)
        return None
    finally:
        try:
            page.close()
        except PlaywrightError:
            pass
