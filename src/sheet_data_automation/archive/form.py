from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from .config import ArchiveConfig

LOGGER = logging.getLogger(__name__)

TIMEOUT_SECONDS = 60


class FormError(RuntimeError):
    pass


class FormAuthError(FormError):
    pass


def webhook_configured(config: ArchiveConfig) -> bool:
    return bool(config.webhook_url and config.webhook_token)


def submit_form(
    config: ArchiveConfig,
    form_type: str,
    form_date: dt.date,
    pdf_path: Path,
) -> None:
    """POST the circular to the Apps Script webhook (apps_script/Code.gs)."""
    if not webhook_configured(config):
        raise FormAuthError("FORM_WEBHOOK_URL and FORM_WEBHOOK_TOKEN must be set")

    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError as exc:
        raise FormError(f"Could not read PDF {pdf_path}: {exc}") from exc

    payload = json.dumps(
        {
            "token": config.webhook_token,
            "type": form_type,
            "date": form_date.isoformat(),
            "filename": pdf_path.name,
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        config.webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    LOGGER.info("Uploading %s circular %s", form_type, pdf_path.name)
    # Apps Script answers with a 302 to googleusercontent.com; urllib follows it as GET.
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise FormAuthError(f"Webhook rejected the request (HTTP {exc.code})") from exc
        raise FormError(f"Webhook returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FormError(f"Webhook request failed: {exc}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FormError(f"Webhook returned non-JSON response: {body[:200]}") from exc
    if not isinstance(result, dict):
        raise FormError(f"Webhook returned an unexpected response: {body[:200]}")

    if not result.get("ok"):
        error = result.get("error", "unknown error")
        if error == "unauthorized":
            raise FormAuthError("Webhook rejected FORM_WEBHOOK_TOKEN")
        raise FormError(f"Webhook error: {error}")

    LOGGER.info("Circular uploaded for %s: %s", form_type, result.get("url"))
