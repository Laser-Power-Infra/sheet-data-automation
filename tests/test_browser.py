from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

import sheet_data_automation.common.browser as browser_module
from sheet_data_automation.common.browser import BrowserSession
from sheet_data_automation.common.errors import ScrapeError


class FakeResponse:
    def __init__(self, body: bytes = b"%PDF-1.4 test", ok: bool = True, status: int = 200):
        self._body = body
        self.ok = ok
        self.status = status

    def body(self) -> bytes:
        return self._body


class FakeRequest:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, timeout: int | None = None, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None and len(self.calls) == 1:
            raise self.error
        return FakeResponse()


class FakeContext:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.page_callback = None

    def on(self, event: str, callback) -> None:
        if event == "page":
            self.page_callback = callback


class FakePage:
    def __init__(self) -> None:
        self.download_callback = None

    def on(self, event: str, callback) -> None:
        if event == "download":
            self.download_callback = callback

    def wait_for_timeout(self, milliseconds: int) -> None:
        pass


class FakePopup:
    def __init__(self, url: str) -> None:
        self.url = url
        self.closed = False

    def wait_for_load_state(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeLocator:
    def __init__(self, context: FakeContext, page: FakePage, href: str) -> None:
        self.context = context
        self.page = page
        self.href = href
        self.clicks = 0

    def scroll_into_view_if_needed(self) -> None:
        pass

    def click(self) -> None:
        self.clicks += 1
        if self.clicks >= 2 and self.context.page_callback is not None:
            self.context.page_callback(FakePopup("https://example.com/price.pdf"))

    def get_attribute(self, name: str) -> str:
        return self.href


def test_fetch_bytes_retries_certificate_errors_without_verification() -> None:
    request = FakeRequest(PlaywrightError("unable to verify the first certificate"))
    session = BrowserSession(FakeContext(request))  # type: ignore[arg-type]

    assert session.fetch_bytes("https://example.com/price.pdf") == b"%PDF-1.4 test"
    assert request.calls == [
        {"url": "https://example.com/price.pdf"},
        {"url": "https://example.com/price.pdf", "ignore_https_errors": True},
    ]


def test_fetch_bytes_does_not_bypass_non_certificate_errors() -> None:
    request = FakeRequest(PlaywrightError("net::ERR_FAILED"))
    session = BrowserSession(FakeContext(request))  # type: ignore[arg-type]

    with pytest.raises(ScrapeError, match="Could not fetch"):
        session.fetch_bytes("https://example.com/price.pdf")

    assert len(request.calls) == 1


def test_reclicks_when_first_click_produces_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_module, "CLICK_WAIT_SECONDS", 0)

    context = FakeContext(FakeRequest())
    page = FakePage()
    locator = FakeLocator(context, page, "https://example.com/price.pdf")
    session = BrowserSession(context)  # type: ignore[arg-type]

    result = session.click_pdf(  # type: ignore[arg-type]
        page,
        locator,
        "https://example.com",
        "test tile",
    )

    assert locator.clicks == 2
    assert result.data == b"%PDF-1.4 test"
    assert result.url == "https://example.com/price.pdf"
