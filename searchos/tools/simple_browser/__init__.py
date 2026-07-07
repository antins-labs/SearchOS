"""Simple Browser (paper §4.2): search / open / find over a line-numbered
page model, with swappable search providers and fetch backends.

Layout:
- ``tools``   — the 3 ``@tool`` shells + ``get_simple_browser_tools``
- ``state``   — ``BrowserState``, fetch/persist, find matching, provider binding
- ``render``  — HTML → line-numbered markdown (pure)
- ``cache``   — disk fetch cache
- ``search/`` — search providers (serper / tavily / ragflow)
- ``backend/``— fetch backends (aiohttp / crawl4ai / jina / search_engine)
"""

from searchos.tools.simple_browser.render import PageContents, process_html
from searchos.tools.simple_browser.state import (
    FETCH_ERROR_SENTINEL,
    BrowserState,
    _get_browser,
    reset_browser,
    reset_browser_for_sub_agent,
    set_browser_provider,
)
from searchos.tools.simple_browser.tools import (
    find,
    get_simple_browser_tools,
    open,
    search,
)

__all__ = [
    "get_simple_browser_tools",
    "search",
    "open",
    "find",
    "set_browser_provider",
    "reset_browser",
    "reset_browser_for_sub_agent",
    "_get_browser",
    "BrowserState",
    "PageContents",
    "process_html",
    "FETCH_ERROR_SENTINEL",
]
