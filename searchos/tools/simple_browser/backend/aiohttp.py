"""aiohttp backend: plain HTTP + lxml + html2text path."""

from __future__ import annotations

import asyncio
import logging
import ssl
from urllib.parse import urlparse

import aiohttp
import certifi

from searchos.tools.simple_browser.backend.base import (
    _HEADERS,
    _MAX_HTML_BYTES,
    _MAX_RETRIES,
    _RETRY_STATUSES,
    FetchResult,
)

logger = logging.getLogger(__name__)


class AiohttpBackend:
    """Plain aiohttp + lxml + html2text path. Delegates HTML→text to
    ``searchos.tools.simple_browser.render.process_html`` (lazy import)."""

    def __init__(
        self,
        *,
        max_retries: int = _MAX_RETRIES,
        max_html_bytes: int = _MAX_HTML_BYTES,
    ) -> None:
        self._max_retries = max_retries
        self._max_html_bytes = max_html_bytes

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult:
        headers = {**_HEADERS, "Referer": f"https://{urlparse(url).netloc}/"}
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        last_error = ""

        for attempt in range(self._max_retries + 1):
            try:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_ctx),
                ) as session:
                    async with session.get(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        allow_redirects=True,
                    ) as resp:
                        if resp.status in _RETRY_STATUSES and attempt < self._max_retries:
                            last_error = f"HTTP {resp.status}"
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        if resp.status != 200:
                            return FetchResult(
                                url=url, title="Error",
                                markdown=f"HTTP {resp.status}",
                                status=resp.status, error=f"HTTP {resp.status}",
                            )

                        ct = resp.headers.get("Content-Type", "")
                        if "text/html" not in ct and "xhtml" not in ct:
                            return FetchResult(
                                url=url, title="Error",
                                markdown=f"Unsupported: {ct}",
                                status=-2, error=f"unsupported content-type: {ct}",
                            )

                        html = await resp.text(errors="replace")
                        if len(html) > self._max_html_bytes:
                            html = html[: self._max_html_bytes]
                        return _html_to_fetch_result(html, url)

            except aiohttp.ClientError as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
            except asyncio.TimeoutError:
                return FetchResult(
                    url=url, title="Error",
                    markdown=f"Fetch failed: timeout after {timeout}s",
                    status=-1, error=f"timeout after {timeout}s",
                )
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
                break

        return FetchResult(
            url=url, title="Error",
            markdown=f"Fetch failed: {last_error}",
            status=0, error=last_error,
        )

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 20.0,
    ) -> list[FetchResult]:
        coros = [self.fetch(u, query=query, timeout=timeout) for u in urls]
        return await asyncio.gather(*coros, return_exceptions=False)

    async def close(self) -> None:
        return None


def _html_to_fetch_result(html: str, url: str) -> FetchResult:
    # Lazy import: render is light, but keep the dependency edge one-way
    # (backend → render, never render → backend).
    from searchos.tools.simple_browser.render import process_html

    pc = process_html(html, url)
    return FetchResult(
        url=pc.url or url,
        title=pc.title or "",
        markdown=pc.text or "",
        html=html,
        links=dict(pc.urls or {}),
    )
