"""Process-level proxy shims for access-skill executors.

Access-skill executors hardcode their own network calls. httpx / requests /
urllib honor the HTTP(S)_PROXY env vars by default, but aiohttp (which defaults
``trust_env=False``) and Playwright (proxy must be passed at ``launch``)
silently ignore the proxy and bare-connect — which times out for overseas
sites in a proxied environment. aiohttp is the dominant library across the
library, so the bulk of skills never reach their target.

Rather than edit every executor, install one set of library-level defaults
once: force aiohttp ``trust_env`` on and inject the env proxy into Playwright
launches that don't already specify one. No-op when no proxy is configured.
Idempotent, and only changes the *default* — explicit caller config (e.g.
``browser_service``) always wins.

Also the single source of truth for CN split-tunnel classification: CN-served
hosts bypass the proxy (direct connection — fastest to their origin, and often
blocked / throttled through an overseas proxy).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_installed = False

# --- CN split-tunnel classification -----------------------------------------

CN_HOST_SUFFIXES: tuple[str, ...] = (".cn",)  # matches *.cn / *.com.cn / *.gov.cn
CN_HOSTS_ON_GLOBAL_TLD: tuple[str, ...] = (
    "baidu.com", "weibo.com", "zhihu.com", "bilibili.com",
    "douban.com", "qq.com", "163.com", "sohu.com", "sina.com",
)


def no_proxy_env_value() -> str:
    """CN bypass list in ``no_proxy`` convention (bare-dot suffix matches any
    subdomain). aiohttp/httpx/requests honor this once trust_env is on."""
    return ",".join([*CN_HOST_SUFFIXES, *CN_HOSTS_ON_GLOBAL_TLD])


def playwright_bypass_value() -> str:
    """CN bypass list in Playwright ``proxy.bypass`` convention (``*.domain``).
    Apex + wildcard so both ``baidu.com`` and ``baike.baidu.com`` match."""
    parts: list[str] = [f"*{s}" for s in CN_HOST_SUFFIXES]
    for d in CN_HOSTS_ON_GLOBAL_TLD:
        parts += [d, f"*.{d}"]
    return ", ".join(parts)


def _env_proxy() -> str | None:
    return (
        os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    )


def install_executor_proxy_shims() -> None:
    """Route executor network libs through the env proxy. Idempotent and cheap
    — safe to call at the top of every ``run_executor``."""
    global _installed
    if _installed:
        return
    proxy = _env_proxy()
    if proxy:
        _install_split_tunnel_bypass()   # CN 站点直连,境外走代理
        _patch_aiohttp()
        _patch_playwright(proxy)
    _installed = True


def _install_split_tunnel_bypass() -> None:
    """Split-tunnel: CN-served hosts bypass the proxy (direct). Merges with any
    user-set no_proxy so we never clobber an explicit setting."""
    existing = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    merged = ",".join(p for p in (existing, no_proxy_env_value()) if p)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged
    logger.info("executor proxy: split-tunnel no_proxy bypass installed")


def _patch_aiohttp() -> None:
    """Default ``aiohttp.ClientSession`` to ``trust_env=True`` so it honors the
    HTTP(S)_PROXY / NO_PROXY env vars (aiohttp defaults it to ``False``)."""
    try:
        import aiohttp
    except Exception:
        return
    orig = aiohttp.ClientSession.__init__
    if getattr(orig, "_sf_proxy_patched", False):
        return

    def __init__(self, *args, **kwargs):  # noqa: N807
        kwargs.setdefault("trust_env", True)
        return orig(self, *args, **kwargs)

    __init__._sf_proxy_patched = True
    aiohttp.ClientSession.__init__ = __init__
    logger.info("executor proxy: aiohttp ClientSession now defaults to trust_env=True")


def _patch_playwright(proxy: str) -> None:
    """Inject ``proxy={"server": ...}`` into Playwright launches that don't
    already specify one."""
    try:
        from playwright.async_api import BrowserType
    except Exception:
        return

    def _wrap(orig):
        async def wrapper(self, *args, **kwargs):
            if not kwargs.get("proxy"):
                kwargs["proxy"] = {"server": proxy, "bypass": playwright_bypass_value()}
            return await orig(self, *args, **kwargs)
        wrapper._sf_proxy_patched = True
        return wrapper

    patched = False
    for meth in ("launch", "launch_persistent_context"):
        orig = getattr(BrowserType, meth, None)
        if orig is None or getattr(orig, "_sf_proxy_patched", False):
            continue
        setattr(BrowserType, meth, _wrap(orig))
        patched = True
    if patched:
        logger.info("executor proxy: Playwright launches now default to the env proxy")
