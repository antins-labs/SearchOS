"""
Browser tool - fetches and parses web pages.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from urllib.parse import urlparse

import aiohttp
import certifi

from ..models import PageContents
from .html_processor import process_html

logger = logging.getLogger(__name__)

# Mimic a real Chrome browser as closely as possible
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# Max retries for transient errors (403, 429, 5xx)
_MAX_RETRIES = 2
_RETRY_STATUSES = {403, 429, 500, 502, 503, 504}


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that works with most sites."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    return ctx


async def fetch_page(
    url: str,
    timeout: float = 30.0,
    max_content_length: int = 1_000_000,
) -> PageContents:
    """Fetch a web page and convert to PageContents.

    Uses aiohttp with realistic browser headers and retry logic.
    """
    headers = {**_HEADERS, "Referer": f"https://{urlparse(url).netloc}/"}
    ssl_ctx = _build_ssl_context()

    last_error: str = ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_ctx),
            ) as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as resp:
                    if resp.status in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                        last_error = f"HTTP {resp.status}"
                        logger.warning(
                            "Fetch %s returned %d, retrying (%d/%d)",
                            url, resp.status, attempt + 1, _MAX_RETRIES,
                        )
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue

                    if resp.status != 200:
                        return PageContents(
                            url=url,
                            title="Error",
                            text=f"Error fetching URL: HTTP {resp.status}",
                            urls={},
                        )

                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" not in content_type and "application/xhtml" not in content_type:
                        return PageContents(
                            url=url,
                            title="Error",
                            text=f"Unsupported content type: {content_type}",
                            urls={},
                        )

                    html = await resp.text(errors="replace")

                    if len(html) > max_content_length:
                        html = html[:max_content_length]

                    return process_html(html=html, url=url)

        except aiohttp.ClientError as e:
            last_error = str(e)
            if attempt < _MAX_RETRIES:
                logger.warning("Fetch %s error: %s, retrying (%d/%d)", url, e, attempt + 1, _MAX_RETRIES)
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
        except Exception as e:
            last_error = str(e)
            logger.error("Unexpected error fetching %s: %s", url, e)
            break

    return PageContents(
        url=url,
        title="Error",
        text=f"Error fetching URL: {last_error}",
        urls={},
    )
