"""aiohttp backend: plain HTTP + lxml + html2text path."""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
        trust_env: bool = False,
        allow_redirects: bool = True,
        allow_json: bool = False,
    ) -> None:
        self._max_retries = max_retries
        self._max_html_bytes = max_html_bytes
        self._trust_env = trust_env
        self._allow_redirects = allow_redirects
        self._allow_json = allow_json

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 20.0,
    ) -> FetchResult:
        headers = {**_HEADERS, "Referer": f"https://{urlparse(url).netloc}/",
                   "Accept-Encoding": "gzip, deflate"}
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        last_error = ""

        for attempt in range(self._max_retries + 1):
            try:
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=ssl_ctx),
                    trust_env=self._trust_env,
                ) as session:
                    async with session.get(
                        url, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        allow_redirects=self._allow_redirects,
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
                        media_type = ct.split(";", 1)[0].strip().lower()
                        if self._allow_json and re.fullmatch(r"application/(?:json|[a-z0-9!#$&^_.+-]+\+json)", media_type):
                            return await _json_response(resp, url, self._max_html_bytes)
                        is_html = (media_type in {"text/html", "application/xhtml+xml"}
                                   if self._allow_json else "text/html" in ct or "xhtml" in ct)
                        if not is_html:
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


async def _json_response(response, url: str, max_bytes: int) -> FetchResult:
    """Opt-in API reader; never turn a partial or ambiguous payload into evidence."""
    body = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        if len(body) + len(chunk) > max_bytes:
            return FetchResult(url=url, title="Error", error=f"JSON response exceeds {max_bytes} bytes")
        body.extend(chunk)

    def invalid_constant(value):
        raise ValueError(f"non-finite number: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(body.decode("utf-8-sig"), parse_constant=invalid_constant,
                           object_pairs_hook=unique_object)
        parts, rendered_bytes = [], 0
        for part in json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False).iterencode(value):
            rendered_bytes += len(part.encode("utf-8"))  # Also reject unpaired escaped surrogates.
            if rendered_bytes > max_bytes * 4:
                raise ValueError(f"rendered JSON exceeds {max_bytes * 4} bytes")
            parts.append(part)
        text = "".join(parts)
    except (ValueError, UnicodeError, RecursionError) as exc:
        return FetchResult(url=url, title="Error", error=f"invalid JSON response: {exc}")
    return FetchResult(url=url, title="JSON response", markdown=text)


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
