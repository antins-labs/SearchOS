"""Shared per-endpoint RPM / TPM rate limiting for LLM calls.

A sliding-60s-window limiter consumed natively via ``BaseChatModel.rate_limiter``.
RPM is pre-paid (acquire books a slot); TPM is post-paid (``record_tokens`` from
a callback feeds the window). Limiters are shared per quota bucket
``(api_base, model, api_key_env)`` across all sessions in the process.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.rate_limiters import BaseRateLimiter

from searchos.util.token_tracker import extract_token_usage

_WINDOW_S = 60.0


class SlidingWindowRateLimiter(BaseRateLimiter):
    """RPM + TPM limiter over a trailing 60s window (0 disables a dimension).

    Thread-safe; the async path polls with ``asyncio.sleep``.
    """

    def __init__(
        self,
        rpm: int = 0,
        tpm: int = 0,
        check_every_s: float = 0.2,
    ) -> None:
        self.rpm = max(0, rpm)
        self.tpm = max(0, tpm)
        self._check_every_s = check_every_s
        self._lock = threading.Lock()
        self._requests: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()
        self._token_sum = 0  # running sum of _token_events, kept in sync

    def _evict(self, now: float) -> None:
        cutoff = now - _WINDOW_S
        while self._requests and self._requests[0] <= cutoff:
            self._requests.popleft()
        while self._token_events and self._token_events[0][0] <= cutoff:
            _, n = self._token_events.popleft()
            self._token_sum -= n

    def _try_acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if self.rpm and len(self._requests) >= self.rpm:
                return False
            if self.tpm and self._token_sum >= self.tpm:
                return False
            self._requests.append(now)
            return True

    def record_tokens(self, n: int) -> None:
        """Report actual token usage of a completed response (TPM feed)."""
        if n <= 0:
            return
        with self._lock:
            self._token_events.append((time.monotonic(), n))
            self._token_sum += n

    def set_limits(self, rpm: int, tpm: int) -> None:
        """Update this shared quota bucket without discarding window history."""
        with self._lock:
            self.rpm = max(0, rpm)
            self.tpm = max(0, tpm)

    # -- BaseRateLimiter interface --

    def acquire(self, *, blocking: bool = True) -> bool:
        if not blocking:
            return self._try_acquire()
        while not self._try_acquire():
            time.sleep(self._check_every_s)
        return True

    async def aacquire(self, *, blocking: bool = True) -> bool:
        if not blocking:
            return self._try_acquire()
        while not self._try_acquire():
            await asyncio.sleep(self._check_every_s)
        return True


class UsageReportingCallback(BaseCallbackHandler):
    """Feeds each response's actual token usage into the limiter's TPM window."""

    def __init__(self, limiter: SlidingWindowRateLimiter) -> None:
        self._limiter = limiter

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        _, _, total, _ = extract_token_usage(response)
        self._limiter.record_tokens(total)


# One (limiter, callback) per bucket; later registrations refresh rpm/tpm.
_registry: dict[tuple[str, str, str], tuple[SlidingWindowRateLimiter, UsageReportingCallback]] = {}
_registry_lock = threading.Lock()


def get_shared_rate_limiter(
    key: tuple[str, str, str],
    rpm: int,
    tpm: int,
) -> tuple[SlidingWindowRateLimiter, UsageReportingCallback]:
    """Process-wide limiter for a quota bucket ``(api_base, model, api_key_env)``."""
    with _registry_lock:
        entry = _registry.get(key)
        if entry is None:
            limiter = SlidingWindowRateLimiter(rpm=rpm, tpm=tpm)
            entry = (limiter, UsageReportingCallback(limiter))
            _registry[key] = entry
        else:
            entry[0].set_limits(rpm, tpm)
        return entry


__all__ = [
    "SlidingWindowRateLimiter",
    "UsageReportingCallback",
    "get_shared_rate_limiter",
]
