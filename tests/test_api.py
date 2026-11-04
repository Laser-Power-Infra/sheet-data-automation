from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

import sheet_data_automation.api.app as api_app
import sheet_data_automation.api.jobs as api_jobs
from sheet_data_automation.api.app import app
from sheet_data_automation.common.result import RunResult


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SHEET_DATA_API_KEY", "secret")
    return TestClient(app)


def _fake_runner(name: str, *, success: bool = True) -> RunResult:
    return RunResult(name, 0 if success else 1, () if success else (f"{name} failed",))


def test_missing_api_key_configuration_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHEET_DATA_API_KEY", "")
    with TestClient(app) as client:
        response = client.get("/api/v1/run-all", headers={"x-api-key": "secret"})
    assert response.status_code == 503


def test_invalid_api_key_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/run-all", headers={"x-api-key": "wrong"})
    assert response.status_code == 401


def test_probe_returns_auth_ok(client: TestClient) -> None:
    response = client.get("/api/v1/run-all", headers={"x-api-key": "secret"})
    assert response.status_code == 200
    assert response.json()["auth"] == "ok"
    assert response.json()["jobs"] == ["cacmai", "balco", "drag"]


def test_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/jobs/nope", headers={"x-api-key": "secret"})
    assert response.status_code == 404


def test_invalid_date_returns_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_jobs, "cacmai_run", lambda **_: _fake_runner("cacmai"))
    response = client.post(
        "/api/v1/jobs/cacmai",
        headers={"x-api-key": "secret"},
        json={"date_override": "not-a-date"},
    )
    assert response.status_code == 422


def test_run_all_runs_jobs_in_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake(name: str):
        def runner(**_):
            calls.append(name)
            return _fake_runner(name)

        return runner

    monkeypatch.setattr(api_jobs, "cacmai_run", fake("cacmai"))
    monkeypatch.setattr(api_jobs, "balco_run", fake("balco"))
    monkeypatch.setattr(api_jobs, "drag_run", fake("drag"))

    response = client.post(
        "/api/v1/run-all",
        headers={"x-api-key": "secret"},
        json={"dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert [job["name"] for job in body["jobs"]] == ["cacmai", "balco", "drag"]
    assert calls == ["cacmai", "balco", "drag"]


def test_run_all_reports_partial_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_jobs, "cacmai_run", lambda **_: _fake_runner("cacmai"))
    monkeypatch.setattr(
        api_jobs,
        "balco_run",
        lambda **_: _fake_runner("balco", success=False),
    )
    monkeypatch.setattr(api_jobs, "drag_run", lambda **_: _fake_runner("drag"))

    response = client.post(
        "/api/v1/run-all",
        headers={"x-api-key": "secret"},
        json={"dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["status"] == "partial"
    assert body["jobs"][1]["success"] is False


def test_busy_run_returns_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_jobs, "cacmai_run", lambda **_: _fake_runner("cacmai"))
    assert api_jobs._lock.acquire(blocking=False)
    try:
        response = client.post(
            "/api/v1/jobs/cacmai",
            headers={"x-api-key": "secret"},
            json={"dry_run": True},
        )
    finally:
        api_jobs._lock.release()
    assert response.status_code == 409


def test_balco_date_override_is_passed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dt.date | None] = []

    def fake(**kwargs):
        seen.append(kwargs.get("date_override"))
        return _fake_runner("balco")

    monkeypatch.setattr(api_jobs, "balco_run", fake)

    response = client.post(
        "/api/v1/jobs/balco",
        headers={"x-api-key": "secret"},
        json={"dry_run": True, "date_override": "2026-10-21"},
    )

    assert response.status_code == 200
    assert seen == [dt.date(2026, 10, 21)]


def test_health_returns_ok_when_config_is_valid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_app, "_config_status", lambda: (True, None))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_returns_503_when_config_is_invalid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_app, "_config_status", lambda: (False, "missing config"))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["config_ok"] is False
