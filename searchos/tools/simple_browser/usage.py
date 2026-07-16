"""Task-local page-cache and browser-backend usage accounting.

The browser service and its disk cache are process-wide, while eval questions
run concurrently.  Process-global counters therefore cannot be subtracted to
obtain per-question usage.  A mutable value stored in a ContextVar gives each
root search session an independent counter that its child agent tasks inherit.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class BrowserUsage:
    served: int = 0
    fetched: int = 0
    stored: int = 0
    coalesced: int = 0
    jina_api_calls: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "served": self.served,
            "fetched": self.fetched,
            "stored": self.stored,
            "coalesced": self.coalesced,
            "jina_api_calls": self.jina_api_calls,
        }


_current_usage: ContextVar[BrowserUsage | None] = ContextVar(
    "sf_browser_usage",
    default=None,
)


def start_tracking() -> BrowserUsage:
    """Bind a fresh counter to the current root search-session task."""
    usage = BrowserUsage()
    _current_usage.set(usage)
    return usage


def get_usage() -> BrowserUsage | None:
    return _current_usage.get()


def record_cache_served() -> None:
    usage = get_usage()
    if usage is not None:
        usage.served += 1


def record_cache_fetched() -> None:
    usage = get_usage()
    if usage is not None:
        usage.fetched += 1


def record_cache_stored() -> None:
    usage = get_usage()
    if usage is not None:
        usage.stored += 1


def record_cache_coalesced() -> None:
    usage = get_usage()
    if usage is not None:
        usage.coalesced += 1


def record_jina_call() -> None:
    usage = get_usage()
    if usage is not None:
        usage.jina_api_calls += 1
