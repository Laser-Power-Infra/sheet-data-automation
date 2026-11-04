from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Self

import pytest

import sheet_data_automation.archive.form as archive_form
import sheet_data_automation.archive.runner as archive_runner
from sheet_data_automation.archive.config import (
    ArchiveConfig,
    folder_for,
    form_type_for,
    nalco_fiscal_year,
)
from sheet_data_automation.archive.form import FormAuthError, FormError, submit_form
from sheet_data_automation.archive.runner import (
    ArchiveManager,
    date_from_url,
    parse_date,
)
from sheet_data_automation.archive.state import load_state, save_state
from sheet_data_automation.archive.storage import filename_for, find_hash, sha256


def make_config(tmp_path, *, webhook: bool = False, max_attempts: int = 10) -> ArchiveConfig:
    return ArchiveConfig(
        root=tmp_path,
        state_file=tmp_path / "state.json",
        webhook_url="https://example.invalid/exec" if webhook else "",
        webhook_token="secret" if webhook else "",
        max_attempts=max_attempts,
    )


def test_nalco_fiscal_year_matches_existing_pattern() -> None:
    assert nalco_fiscal_year(dt.date(2026, 10, 24)) == "2026-27"
    assert nalco_fiscal_year(dt.date(2026, 4, 1)) == "2026-27"
    assert nalco_fiscal_year(dt.date(2027, 1, 1)) == "2026-27"
    assert nalco_fiscal_year(dt.date(2027, 4, 1)) == "2027-28"


def test_folder_layouts(tmp_path) -> None:
    value = dt.date(2026, 10, 24)
    assert folder_for("BALCO", value, tmp_path) == tmp_path / "Balco2" / "Oct 2026"
    assert folder_for("HINDALCO", value, tmp_path) == tmp_path / "HINDALCO2" / "Oct"
    assert folder_for("NALCO", value, tmp_path) == tmp_path / "NALCO" / "2026-27" / "Oct"


def test_filename_suffixes() -> None:
    assert (
        filename_for("BALCO", "https://x/PrimaryAL-PriceList-24.10.2026.pdf")
        == "PrimaryAL-PriceList-24.10.2026 Balco.pdf"
    )
    assert (
        filename_for("HINDALCO", "https://x/primary-ready-reckoner-15-october-2026.pdf")
        == "primary-ready-reckoner-15-october-2026 Hindalco.pdf"
    )
    assert filename_for("NALCO", "https://x/Ingot-24-10-26.pdf") == "Ingot-24-10-26 Nalco.pdf"


def test_date_parsing() -> None:
    assert parse_date("24.10.2026") == dt.date(2026, 10, 24)
    assert date_from_url("https://x/Ingot-24-10-26.pdf") == dt.date(2026, 10, 24)
    assert date_from_url("https://x/PrimaryAL-PriceList-24.10.2026.pdf") == dt.date(2026, 10, 24)
    assert date_from_url("https://x/primary-ready-reckoner-15-october-2026.pdf") == dt.date(
        2026, 10, 15
    )


def test_hash_dedupe(tmp_path) -> None:
    folder = tmp_path / "Balco2" / "Oct 2026"
    folder.mkdir(parents=True)
    data = b"%PDF-test"
    path = folder / "one.pdf"
    path.write_bytes(data)

    assert find_hash(folder, sha256(data)) == path
    assert find_hash(folder, sha256(b"other")) is None


def test_archive_manager_saves_pending_without_webhook(tmp_path) -> None:
    config = make_config(tmp_path)
    manager = ArchiveManager(config)
    data = b"%PDF-test"
    manager.archive(
        "BALCO",
        data,
        "https://x/PrimaryAL-PriceList-24.10.2026.pdf",
        "24.10.2026",
        dt.date(2026, 10, 24),
    )

    expected = tmp_path / "Balco2" / "Oct 2026" / "PrimaryAL-PriceList-24.10.2026 Balco.pdf"
    assert expected.is_file()
    entry = load_state(config.state_file)[sha256(data)]
    assert entry["form_status"] == "pending"
    assert entry["attempts"] == 0
    assert entry["form_date"] == "2026-10-24"
    assert entry["path"] == "Balco2/Oct 2026/PrimaryAL-PriceList-24.10.2026 Balco.pdf"


def test_new_month_and_fiscal_year_folders_are_created(tmp_path) -> None:
    manager = ArchiveManager(make_config(tmp_path))
    data = b"%PDF-test"
    cases = [
        ("BALCO", "02.11.2026", "Balco2/Nov 2026"),
        ("HINDALCO", "02.11.2026", "HINDALCO2/Nov"),
        ("NALCO", "01.04.2027", "NALCO/2027-28/Apr"),
        ("HINDALCO", "04.01.2027", "HINDALCO2/Jan 2027"),
        ("BALCO", "04.01.2027", "Balco2/Jan 2027"),
    ]
    for source, date_text, folder in cases:
        assert not (tmp_path / folder).exists()
        manager.archive(source, data, f"https://x/c-{source}.pdf", date_text, dt.date(2026, 10, 27))
        assert len(list((tmp_path / folder).glob("*.pdf"))) == 1


def test_archive_manager_retries_pending_form(tmp_path, monkeypatch) -> None:
    submitted: list[str] = []

    def fake_submit(config, form_type, form_date, pdf_path):
        submitted.append(form_type)

    monkeypatch.setattr(archive_runner, "submit_form", fake_submit)
    config = make_config(tmp_path, webhook=True)
    manager = ArchiveManager(config)
    data = b"%PDF-test"
    url = "https://x/Ingot-24-10-26.pdf"
    manager.archive("NALCO", data, url, "24.10.2026", dt.date(2026, 10, 24))
    manager.archive("NALCO", data, url, "24.10.2026", dt.date(2026, 10, 24))

    assert submitted == ["Nalco"]
    assert load_state(config.state_file)[sha256(data)]["form_status"] == "submitted"


def test_retry_pending_submits_old_entries_and_legacy_paths(tmp_path, monkeypatch) -> None:
    submitted: list[Path] = []
    monkeypatch.setattr(
        archive_runner,
        "submit_form",
        lambda config, form_type, form_date, pdf_path: submitted.append(pdf_path),
    )
    config = make_config(tmp_path, webhook=True)
    pdf = tmp_path / "Balco2" / "Oct 2026" / "x Balco.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-old")
    save_state(
        config.state_file,
        {
            "abc": {
                "source": "BALCO",
                "form_date": "2026-10-26",
                "path": r"W:\ALU price history\Balco2\Oct 2026\x Balco.pdf",
                "form_status": "pending",
                "attempts": 0,
                "last_error": None,
            }
        },
    )

    ArchiveManager(config).retry_pending()

    assert submitted == [pdf]
    assert load_state(config.state_file)["abc"]["form_status"] == "submitted"


def test_retry_sends_circular_date_not_run_date(tmp_path, monkeypatch) -> None:
    dates: list[dt.date] = []
    monkeypatch.setattr(
        archive_runner,
        "submit_form",
        lambda config, form_type, form_date, pdf_path: dates.append(form_date),
    )
    config = make_config(tmp_path, webhook=True)
    pdf = tmp_path / "Balco2" / "Oct 2026" / "x Balco.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-old")
    save_state(
        config.state_file,
        {
            "abc": {
                "source": "HINDALCO",
                "circular_date": "2026-10-24",
                "form_date": "2026-10-26",
                "path": "Balco2/Oct 2026/x Balco.pdf",
                "form_status": "pending",
                "attempts": 0,
            }
        },
    )

    ArchiveManager(config).retry_pending()

    assert dates == [dt.date(2026, 10, 24)]


def test_vedanta_is_not_a_form_type() -> None:
    with pytest.raises(ValueError):
        form_type_for("VEDANTA")


def test_submit_marks_failed_after_max_attempts(tmp_path, monkeypatch) -> None:
    def failing_submit(config, form_type, form_date, pdf_path):
        raise FormError("boom")

    monkeypatch.setattr(archive_runner, "submit_form", failing_submit)
    config = make_config(tmp_path, webhook=True, max_attempts=2)
    manager = ArchiveManager(config)
    data = b"%PDF-test"
    url = "https://x/Ingot-24-10-26.pdf"
    manager.archive("NALCO", data, url, "24.10.2026", dt.date(2026, 10, 24))
    assert manager.state[sha256(data)]["form_status"] == "pending"
    manager.retry_pending()
    entry = load_state(config.state_file)[sha256(data)]
    assert entry["form_status"] == "failed"
    assert entry["attempts"] == 2


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        return None


def test_submit_form_posts_json(tmp_path, monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        return FakeResponse({"ok": True, "url": "https://drive/x"})

    monkeypatch.setattr(archive_form.urllib.request, "urlopen", fake_urlopen)
    pdf = tmp_path / "a Nalco.pdf"
    pdf.write_bytes(b"%PDF-1")

    submit_form(make_config(tmp_path, webhook=True), "Nalco", dt.date(2026, 10, 26), pdf)

    assert captured["url"] == "https://example.invalid/exec"
    payload = captured["payload"]
    assert payload["token"] == "secret"
    assert payload["type"] == "Nalco"
    assert payload["date"] == "2026-10-26"
    assert payload["filename"] == "a Nalco.pdf"
    assert payload["pdf_base64"] == "JVBERi0x"


def test_submit_form_errors(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1")
    config = make_config(tmp_path, webhook=True)

    with pytest.raises(FormAuthError):
        submit_form(make_config(tmp_path), "Nalco", dt.date(2026, 10, 26), pdf)

    monkeypatch.setattr(
        archive_form.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"ok": False, "error": "unauthorized"}),
    )
    with pytest.raises(FormAuthError):
        submit_form(config, "Nalco", dt.date(2026, 10, 26), pdf)

    monkeypatch.setattr(
        archive_form.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"ok": False, "error": "missing field"}),
    )
    with pytest.raises(FormError, match="missing field"):
        submit_form(config, "Nalco", dt.date(2026, 10, 26), pdf)
