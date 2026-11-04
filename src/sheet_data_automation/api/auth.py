from __future__ import annotations

import hashlib
import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException

API_KEY_ENV = "SHEET_DATA_API_KEY"
API_KEY_HEADER = "x-api-key"


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> None:
    expected = os.getenv(API_KEY_ENV, "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=f"{API_KEY_ENV} is not configured on the server.",
        )
    if not x_api_key or not hmac.compare_digest(_digest(x_api_key), _digest(expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key.")
