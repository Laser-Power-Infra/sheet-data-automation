from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sheet_data_automation.api.app as api_app
import sheet_data_automation.api.jobs as api_jobs
import sheet_data_automation.oneoff.importers as importers
from sheet_data_automation.api.app import app

ROOT = Path(__file__).resolve().parents[1]
PDFS = {
    "cacmai": ROOT / "Doc13L-108.pdf",
    "ieema-conductor": ROOT / "01-10-2026.pdf",
    "ieema-cables": ROOT / "01-10-2026 (1).pdf",
    "ieema-mvcc": ROOT / "October 2026.pdf",
    "cacmai-nov": ROOT / "Doc13L-109A.pdf",
}
KEY = {"x-api-key": "secret"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SHEET_DATA_API_KEY", "secret")
    calls: list[bool] = []

    formats: list[tuple] = []

    class FakeSheet:
        def format(self, rng, fmt):
            formats.append((rng, fmt["numberFormat"]["pattern"]))

    def fake_sync(_ws, rows, *, apply, **_kw):
        calls.append(apply)
        return {"dates": len(rows), "rows": 1, "cells": 2, "missing": 0,
                "missing_dates": [], "preview": [{"date": "2026-10-01", "row": 5, "changes": {"C": 1}}]}

    monkeypatch.setattr(importers, "open_worksheet", lambda *_a, **_k: FakeSheet())
    monkeypatch.setattr(importers, "load_app_config", lambda: object())
    monkeypatch.setattr(importers, "sync_rows", fake_sync)
    test_client = TestClient(app)
    test_client.sync_calls = calls  # type: ignore[attr-defined]
    test_client.formats = formats  # type: ignore[attr-defined]
    return test_client


def _post(client: TestClient, kind: str, data: bytes, apply: bool = False, headers=KEY):
    return client.post(
        f"/api/v1/uploads/{kind}",
        files={"file": ("x.pdf", data, "application/pdf")},
        data={"apply": "true" if apply else "false"},
        headers=headers,
    )


def test_index_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Circular upload" in response.text


def test_no_key_needed(client: TestClient) -> None:
    assert _post(client, "cacmai", b"hello", headers={}).status_code == 422


def test_unknown_kind_404(client: TestClient) -> None:
    assert _post(client, "nope", b"%PDF").status_code == 404


def test_non_pdf_422(client: TestClient) -> None:
    response = _post(client, "cacmai", b"hello")
    assert response.status_code == 422
    assert "not a PDF" in response.json()["error"]


def test_oversize_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_app, "MAX_PDF_BYTES", 10)
    assert _post(client, "cacmai", b"%PDF" + b"0" * 20).status_code == 413


def test_busy_409(client: TestClient) -> None:
    with api_jobs.exclusive():
        assert _post(client, "cacmai", b"%PDF").status_code == 409


@pytest.mark.parametrize("kind", PDFS)
def test_valid_pdf_validate_then_apply(client: TestClient, kind: str) -> None:
    if not PDFS[kind].is_file():
        pytest.skip("sample PDF not available")
    data = PDFS[kind].read_bytes()
    kind = "cacmai" if kind == "cacmai-nov" else kind

    check = _post(client, kind, data)
    assert check.status_code == 200, check.text
    assert check.json()["applied"] is False
    assert client.sync_calls == [False]  # type: ignore[attr-defined]
    assert client.formats == []  # type: ignore[attr-defined]

    done = _post(client, kind, data, apply=True)
    assert done.status_code == 200
    assert client.sync_calls == [False, True]  # type: ignore[attr-defined]
    if kind == "ieema-mvcc":
        assert client.formats == [("AD5:AD5", "0.00")]  # type: ignore[attr-defined]


def test_wrong_pdf_in_wrong_card(client: TestClient) -> None:
    if not PDFS["ieema-cables"].is_file():
        pytest.skip("sample PDF not available")
    response = _post(client, "ieema-conductor", PDFS["ieema-cables"].read_bytes())
    assert response.status_code == 422
    assert "IEEMA Cables circular" in response.json()["error"]
    assert client.sync_calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("kind", "pdf_kind", "label"),
    [
        ("ieema-cables", "ieema-mvcc", "IEEMA MVCC circular"),
        ("ieema-mvcc", "ieema-cables", "IEEMA Cables circular"),
    ],
)
def test_cables_and_mvcc_not_interchangeable(client: TestClient, kind, pdf_kind, label) -> None:
    if not PDFS[pdf_kind].is_file():
        pytest.skip("sample PDF not available")
    response = _post(client, kind, PDFS[pdf_kind].read_bytes())
    assert response.status_code == 422
    assert label in response.json()["error"]
