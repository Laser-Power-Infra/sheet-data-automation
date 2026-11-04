from __future__ import annotations

import logging
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)

PdfCallback = Callable[[bytes, str, str | None], None]


def notify_pdf(
    callback: PdfCallback | None,
    data: bytes,
    url: str,
    date_text: str | None,
) -> None:
    if callback is None:
        return
    try:
        callback(data, url, date_text)
    except Exception:
        LOGGER.exception("PDF callback failed for %s", url)
