"""浏览器抓取缓存、跨进程请求锁与运行计量。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import IO, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from searchos.tools.simple_browser.fetchers.base import FetchResult


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


logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]


# Tracking / session params that don't change the page content. Stripping
# them collapses URL variants (same page reached via different campaigns,
# referrers, or session IDs) onto a single cache key.
_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_brand", "utm_social", "utm_social-type",
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_cid", "mc_eid",
    "_ga", "_gl", "ref", "ref_src", "ref_url", "referrer", "source",
    "from", "spm", "share_source", "share_token", "share_from",
    "wt_mc", "_hsenc", "_hsmi", "hsCtaTracking", "vero_id", "vero_conv",
})


def _normalize_url(url: str) -> str:
    """Canonicalize a URL for cache keying.

    - Lowercase scheme and host (URLs are case-insensitive there).
    - Drop the fragment (``#section``) — it never reaches the server.
    - Strip well-known tracking params (utm_*, fbclid, gclid, ...).
    - Sort remaining query params for stable ordering.
    - Collapse a lone trailing slash on the path so ``/foo`` and ``/foo/``
      map to the same key (but only when there's no query, to avoid
      breaking servers that distinguish them — most don't, but the path
      itself is what we treat as semantically identical).
    """
    if not url:
        return url
    try:
        s = urlsplit(url)
    except Exception:
        return url
    scheme = (s.scheme or "").lower()
    netloc = (s.netloc or "").lower()
    path = s.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    qs_pairs = [
        (k, v) for k, v in parse_qsl(s.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    qs_pairs.sort()
    query = urlencode(qs_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def _key(url: str, *, namespace: str = "") -> str:
    normalized = _normalize_url(url)
    material = f"{namespace.strip()}\n{normalized}" if namespace.strip() else normalized
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DiskFetchCache:
    """Lock-free, append-only on-disk cache. Safe for concurrent reads;
    concurrent writes for the same URL race-resolve via os.replace."""

    def __init__(self, root: str | Path, *, namespace: str = "") -> None:
        self._root = Path(root).expanduser()
        self._namespace = namespace.strip()
        self._root.mkdir(parents=True, exist_ok=True)
        # served = served from cache (no network)
        # fetched = had to go to network (cache lookup failed)
        # stored = persisted to disk (fresh fetches; html-upgrade rewrites
        #          opt out via put(count=False))
        self._served = 0
        self._fetched = 0
        self._stored = 0
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "served": self._served,
                "fetched": self._fetched,
                "stored": self._stored,
            }

    def _path_for(self, url: str) -> Path:
        h = _key(url, namespace=self._namespace)
        return self._root / h[:2] / f"{h}.json"

    def _lock_path_for(self, url: str) -> Path:
        h = _key(url, namespace=self._namespace)
        return self._root / ".fetch_locks" / h[:2] / f"{h}.lock"

    def peek(self, url: str) -> FetchResult | None:
        """Read a cached result without changing any usage counters."""
        if not url:
            return None
        path = self._path_for(url)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("disk cache read failed: %s", path, exc_info=True)
            return None
        return FetchResult(
            url=data.get("url", url),
            title=data.get("title", ""),
            markdown=data.get("markdown", ""),
            html=data.get("html", ""),
            links=data.get("links", {}) or {},
            status=int(data.get("status", 200)),
            error=data.get("error", ""),
        )

    def record_served(self) -> None:
        with self._lock:
            self._served += 1
        record_cache_served()

    def record_fetched(self) -> None:
        with self._lock:
            self._fetched += 1
        record_cache_fetched()

    def open_fetch_lock(self, url: str) -> IO[bytes]:
        """Open the cross-process lock file for one normalized URL.

        Lock files are intentionally retained. Unlinking an active flock path
        can let a third process lock a new inode and bypass current waiters.
        """
        path = self._lock_path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open("a+b")

    @staticmethod
    def try_acquire_fetch_lock(handle: IO[bytes]) -> bool:
        """Attempt a non-blocking flock; safe to poll from an async loop."""
        if fcntl is None:
            return True
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    @staticmethod
    def release_fetch_lock(handle: IO[bytes] | None) -> None:
        if handle is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def get(self, url: str) -> FetchResult | None:
        if not url:
            return None
        result = self.peek(url)
        if result is None:
            self.record_fetched()
            return None
        self.record_served()
        return result

    def put(self, result: FetchResult, *, count: bool = True) -> None:
        """Write ``result`` to disk. ``count=False`` skips the writes
        counter (use for re-writes that aren't fresh fetches)."""
        if not result.ok or not result.url:
            return
        path = self._path_for(result.url)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            payload: dict[str, Any] = asdict(result)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
            if count:
                with self._lock:
                    self._stored += 1
                record_cache_stored()
        except Exception:
            logger.debug("disk cache write failed: %s", path, exc_info=True)
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
