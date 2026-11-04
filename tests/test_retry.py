from __future__ import annotations

import gspread
import pytest
import requests

from sheet_data_automation.common.retry import is_transient_error, retry_transient


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "error"

    def json(self) -> dict:
        return {
            "error": {
                "code": self.status_code,
                "message": "test error",
                "status": "TEST",
            }
        }


def _api_error(status_code: int) -> gspread.exceptions.APIError:
    return gspread.exceptions.APIError(FakeResponse(status_code))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sheet_data_automation.common.retry.time.sleep", lambda _: None)


def test_retries_transient_error_then_succeeds() -> None:
    calls: list[int] = []

    @retry_transient
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise requests.exceptions.ConnectionError("offline")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_does_not_retry_non_transient_error() -> None:
    calls: list[int] = []

    @retry_transient
    def broken() -> None:
        calls.append(1)
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        broken()
    assert len(calls) == 1


def test_retries_transient_api_error() -> None:
    calls: list[int] = []

    @retry_transient
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _api_error(503)
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 2


def test_does_not_retry_permission_api_error() -> None:
    calls: list[int] = []

    @retry_transient
    def broken() -> None:
        calls.append(1)
        raise _api_error(403)

    with pytest.raises(gspread.exceptions.APIError):
        broken()
    assert len(calls) == 1


def test_is_transient_error_classification() -> None:
    assert is_transient_error(_api_error(429))
    assert is_transient_error(requests.exceptions.Timeout())
    assert not is_transient_error(_api_error(400))
    assert not is_transient_error(ValueError())
