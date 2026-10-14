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
import functools
import inspect

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
        or os.getenv("ALL_PROXY") or os.getenv("all_proxy")
    )


def install_executor_proxy_shims() -> None:
    """Route executor network libs through the env proxy. Idempotent and cheap
    — safe to call at the top of every ``run_executor``."""
    global _installed
    if _installed:
        return
    proxy = _env_proxy()
    mode = os.environ.get('SEARCHOS_PROXY_MODE', 'inherit')
    if proxy or mode == 'direct':
        if mode == 'inherit' and proxy:
            _install_split_tunnel_bypass()
        _patch_aiohttp()
        _patch_playwright(proxy, mode)
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


def _patch_playwright(proxy: str | None, mode: str = 'inherit') -> None:
    """仅修改隔离探测 worker；同步/异步 Playwright 使用同一代理选择。"""
    try:
        from playwright.async_api import BrowserType as AsyncBrowserType
        from playwright.sync_api import BrowserType as SyncBrowserType
    except Exception:
        return

    def _wrap(orig):
        def options(kwargs):
            if mode == 'direct':
                kwargs.pop('proxy', None)
                kwargs['args'] = [arg for arg in (kwargs.get('args') or []) if not arg.startswith(('--proxy-server', '--proxy-pac-url'))] + ['--no-proxy-server']
            elif mode == 'proxy' or not kwargs.get('proxy'):
                kwargs['proxy'] = {'server': proxy, 'bypass': playwright_bypass_value() if mode == 'inherit' else 'localhost,127.0.0.1,::1'}
            return kwargs
        @functools.wraps(orig)
        async def async_wrapper(self, *args, **kwargs):
            kwargs = options(kwargs)
            return await orig(self, *args, **kwargs)
        @functools.wraps(orig)
        def sync_wrapper(self, *args, **kwargs):
            return orig(self, *args, **options(kwargs))
        wrapper = async_wrapper if inspect.iscoroutinefunction(orig) else sync_wrapper
        wrapper._sf_proxy_patched = True
        return wrapper

    patched = False
    for browser_type in (AsyncBrowserType, SyncBrowserType):
        for meth in ("launch", "launch_persistent_context"):
            orig = getattr(browser_type, meth, None)
            if orig is None or getattr(orig, "_sf_proxy_patched", False):
                continue
            setattr(browser_type, meth, _wrap(orig))
            patched = True
    if patched:
        logger.info("executor proxy: Playwright launches now default to the env proxy")
