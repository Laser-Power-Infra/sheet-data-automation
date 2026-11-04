from __future__ import annotations

import datetime as dt

import pytest

import sheet_data_automation.archive.runner as archive_runner
from sheet_data_automation.archive.config import ArchiveConfig
from sheet_data_automation.archive.runner import ArchiveManager
from sheet_data_automation.archive.state import load_state, save_state
from sheet_data_automation.archive.storage import filename_for, sha256


def make_config(tmp_path, *, webhook: bool = False, max_attempts: int = 10) -> ArchiveConfig:
    return ArchiveConfig(
        root=tmp_path,
        state_file=tmp_path / "state.json",
        webhook_url="https://example.invalid/exec" if webhook else "",
        webhook_token="secret" if webhook else "",
        max_attempts=max_attempts,
    )


def test_corrupt_state_is_backed_up(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("{not json", encoding="utf-8")

    assert load_state(state_file) == {}
    assert list(tmp_path.glob("state.corrupt-*.json"))


def test_orphan_pdf_is_recovered_and_submitted(tmp_path, monkeypatch) -> None:
    submitted: list[str] = []
    monkeypatch.setattr(
        archive_runner,
        "submit_form",
        lambda config, form_type, form_date, pdf_path: submitted.append(str(pdf_path)),
    )
    config = make_config(tmp_path, webhook=True)
    data = b"%PDF-orphan"
    pdf = tmp_path / "Balco2" / "Oct 2026" / "x Balco.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(data)

    ArchiveManager(config).archive(
        "BALCO",
        data,
        "https://x/x.pdf",
        "24.10.2026",
        dt.date(2026, 10, 24),
    )

    assert submitted == [str(pdf)]
    entry = load_state(config.state_file)[sha256(data)]
    assert entry["form_status"] == "submitted"


def test_missing_pending_file_counts_attempts_and_fails(tmp_path, monkeypatch) -> None:
    config = make_config(tmp_path, webhook=True, max_attempts=1)
    save_state(
        config.state_file,
        {
            "abc": {
                "source": "NALCO",
                "path": "missing.pdf",
                "form_status": "pending",
                "attempts": 0,
            }
        },
    )
    monkeypatch.setattr(
        archive_runner,
        "submit_form",
        lambda *args, **kwargs: pytest.fail("should not submit a missing file"),
    )

    ArchiveManager(config).retry_pending()

    entry = load_state(config.state_file)["abc"]
    assert entry["attempts"] == 1
    assert entry["form_status"] == "failed"
    assert "file not found" in entry["last_error"]


def test_filename_is_sanitized() -> None:
    name = filename_for("BALCO", "https://x/a:b.pdf")
    assert ":" not in name
    assert name.endswith(" Balco.pdf")
