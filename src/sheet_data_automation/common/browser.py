from __future__ import annotations

import logging
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import (
    BrowserContext,
    Download,
    Locator,
    Page,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .errors import ScrapeError

LOGGER = logging.getLogger(__name__)

TIMEOUT_MS = 60000
CLICK_ATTEMPTS = 3
CLICK_WAIT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class PdfDownload:
    data: bytes
    url: str


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


class BrowserSession:
    def __init__(self, context: BrowserContext, timeout_ms: int = TIMEOUT_MS) -> None:
        self.context = context
        self.timeout_ms = timeout_ms

    def new_page(self) -> Page:
        page = self.context.new_page()
        page.set_default_timeout(self.timeout_ms)
        return page

    def fetch_bytes(self, url: str) -> bytes:
        try:
            response = self.context.request.get(url, timeout=self.timeout_ms)
        except PlaywrightError as exc:
            if "certificate" not in str(exc).lower():
                raise ScrapeError(f"Could not fetch {url}: {exc}") from exc
            LOGGER.warning("TLS verification failed for %s; retrying without verification", url)
            try:
                response = self.context.request.get(
                    url,
                    timeout=self.timeout_ms,
                    ignore_https_errors=True,
                )
            except PlaywrightError as retry_exc:
                raise ScrapeError(f"Could not fetch {url}: {retry_exc}") from retry_exc
        if not response.ok:
            raise ScrapeError(f"HTTP {response.status} while fetching {url}")
        try:
            body = response.body()
        except PlaywrightError as exc:
            raise ScrapeError(f"Could not read response body from {url}: {exc}") from exc
        if not is_pdf(body):
            raise ScrapeError(f"Fetched content is not a PDF: {url}")
        return body

    def click_pdf(
        self,
        page: Page,
        locator: Locator,
        page_url: str,
        label: str,
        logs_dir: Path | None = None,
    ) -> PdfDownload:
        downloads: list[Download] = []
        popups: list[Page] = []

        def on_download(download: Download) -> None:
            downloads.append(download)

        def on_popup(popup: Page) -> None:
            popups.append(popup)

        page.on("download", on_download)
        self.context.on("page", on_popup)

        try:
            for attempt in range(1, CLICK_ATTEMPTS + 1):
                LOGGER.info("Click attempt %s/%s: %s", attempt, CLICK_ATTEMPTS, label)
                try:
                    locator.scroll_into_view_if_needed()
                    locator.click()
                except PlaywrightError as exc:
                    LOGGER.warning("Click attempt %s/%s failed: %s", attempt, CLICK_ATTEMPTS, exc)

                deadline = time.monotonic() + CLICK_WAIT_SECONDS
                while time.monotonic() < deadline:
                    if downloads:
                        break
                    if any(p.url not in ("", "about:blank") for p in popups):
                        page.wait_for_timeout(1500)
                        break
                    page.wait_for_timeout(200)

                if downloads:
                    return _read_download(downloads[0])

                if popups:
                    popup = popups[-1]
                    if popup.url.startswith("http"):
                        try:
                            popup.wait_for_load_state("domcontentloaded", timeout=10000)
                        except PlaywrightTimeoutError:
                            pass
                        try:
                            LOGGER.info("PDF opened in a new tab: %s", popup.url)
                            return PdfDownload(self.fetch_bytes(popup.url), popup.url)
                        except ScrapeError as exc:
                            LOGGER.warning("Popup PDF could not be read: %s", exc)

                    LOGGER.warning("Popup did not yield a PDF (url=%s)", popup.url)
                    for item in popups:
                        try:
                            item.close()
                        except PlaywrightError:
                            pass
                    popups.clear()

                if attempt < CLICK_ATTEMPTS:
                    LOGGER.info("No PDF yet; re-clicking %s", label)
                    page.wait_for_timeout(1000)

            try:
                href = locator.get_attribute("href")
            except PlaywrightError:
                href = None

            if href:
                pdf_url = urljoin(page_url, href)
                LOGGER.warning("Click attempts exhausted; fetching href directly: %s", pdf_url)
                return PdfDownload(self.fetch_bytes(pdf_url), pdf_url)

            raise ScrapeError(f"No download, popup, or href found for {label}")
        except ScrapeError:
            dump_failure(page, logs_dir, label)
            raise


@contextmanager
def browser_session(headless: bool = True) -> Iterator[BrowserSession]:
    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            try:
                browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context(
                    accept_downloads=True,
                    viewport={"width": 1440, "height": 900},
                    user_agent=USER_AGENT,
                )
            except PlaywrightError as exc:
                raise ScrapeError(
                    "Could not start Chromium. Install the browser with "
                    f"'py -m playwright install chromium'. {exc}"
                ) from exc
            yield BrowserSession(context)
        finally:
            for resource in (context, browser):
                if resource is None:
                    continue
                try:
                    resource.close()
                except PlaywrightError as exc:
                    LOGGER.warning("Could not close browser resource: %s", exc)


def _read_download(download: Download) -> PdfDownload:
    failure = download.failure()
    if failure:
        raise ScrapeError(f"PDF download failed: {failure}")
    with tempfile.TemporaryDirectory(prefix="price-pdf-") as tmp:
        path = Path(tmp) / "document.pdf"
        download.save_as(path)
        data = path.read_bytes()
    if not is_pdf(data):
        raise ScrapeError(f"Downloaded file is not a PDF: {download.url}")
    return PdfDownload(data, download.url)


def dump_failure(page: Page, logs_dir: Path | None, label: str) -> None:
    if logs_dir is None:
        return
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_label = "".join(char if char.isalnum() else "-" for char in label).strip("-")
        html_path = logs_dir / f"failure-{safe_label}-{stamp}.html"
        png_path = logs_dir / f"failure-{safe_label}-{stamp}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(png_path), full_page=True)
        LOGGER.error("Saved failure diagnostics to %s and %s", html_path, png_path)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not save failure diagnostics: %s", exc)
