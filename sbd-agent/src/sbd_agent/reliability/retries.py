"""Retries, timeouts, and idempotent tool wrappers for agent reliability."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryError(RuntimeError):
    pass


def with_retry(
    fn: Callable[[], T],
    *,
    retries: int = 2,
    backoff_ms: float = 50,
    retry_on: tuple[type[BaseException], ...] = (TimeoutError, RuntimeError),
) -> T:
    last: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if attempt >= retries:
                break
            time.sleep((backoff_ms / 1000.0) * (2**attempt))
    raise RetryError(f"Failed after {retries + 1} attempts: {last}") from last


def with_timeout(fn: Callable[[], T], timeout_ms: float) -> T:
    """Soft timeout for deterministic local tools (cooperative)."""
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms > timeout_ms:
        raise TimeoutError(f"Tool exceeded timeout ({elapsed_ms:.0f}ms > {timeout_ms}ms)")
    return result
