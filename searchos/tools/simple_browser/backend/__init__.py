"""Fetch backends (paper §4.2): the page-fetching half of Simple Browser.

``BrowserService`` is the facade consumers use; concrete backends are
selected by the ``browser_backend`` setting via ``_build_default_backend``.
"""

from searchos.tools.simple_browser.backend.base import (
    BrowserBackend,
    BrowserService,
    FetchResult,
)
from searchos.tools.simple_browser.backend.search_engine import (
    clear_search_results,
    register_search_results,
)

__all__ = [
    "BrowserBackend",
    "BrowserService",
    "FetchResult",
    "register_search_results",
    "clear_search_results",
]
