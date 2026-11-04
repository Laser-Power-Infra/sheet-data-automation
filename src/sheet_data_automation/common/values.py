from __future__ import annotations

from collections.abc import Callable

from .google import is_filled


def same_number(current: object, value: float) -> bool:
    try:
        return abs(float(str(current)) - value) < 1e-9
    except (TypeError, ValueError):
        return False


def decide_value(
    current: object,
    previous: object,
    fetched: float | None,
) -> tuple[object | None, str]:
    if fetched is not None:
        if is_filled(current) and same_number(current, fetched):
            return None, "unchanged"
        return fetched, "updated" if is_filled(current) else "filled"
    if is_filled(current):
        return None, "keep"
    if is_filled(previous):
        return previous, "carried"
    return None, "empty"


def previous_value(
    read: Callable[[int], object],
    row: int,
    *,
    limit: int = 20,
) -> tuple[object | None, int | None]:
    for offset in range(1, limit + 1):
        candidate = row - offset
        if candidate < 1:
            break
        value = read(candidate)
        if is_filled(value):
            return value, candidate
    return None, None
