from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable

import gspread
import requests

LOGGER = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 2.0

def is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, gspread.exceptions.APIError):
        code = getattr(exc, "code", None)
        if code is None:
            response = getattr(exc, "response", None)
            code = getattr(response, "status_code", None)
        return code in TRANSIENT_STATUS_CODES
    return isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    )


def retry_call[**P, R](
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    for attempt in range(1, DEFAULT_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if attempt >= DEFAULT_ATTEMPTS or not is_transient_error(exc):
                raise
            delay = DEFAULT_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            LOGGER.warning(
                "Transient Google Sheets error (attempt %s/%s); retrying in %.1fs: %s",
                attempt,
                DEFAULT_ATTEMPTS,
                delay,
                exc,
            )
            time.sleep(delay)
    raise AssertionError("unreachable")


def retry_transient[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return retry_call(func, *args, **kwargs)

    return wrapper
