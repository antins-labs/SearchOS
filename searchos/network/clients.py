"""客户端原生代理接入与明确可重试读取的反馈。"""
from __future__ import annotations

import ssl
import threading
import time

import httpx


def _certificate_error(exc):
    while exc:
        if isinstance(exc, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


async def _alternative(context, url, allowed_urls, timeout):
    from urllib.parse import urlsplit

    from . import _gateway_loop
    value = urlsplit(str(url))
    host, port = value.hostname, value.port or (443 if value.scheme == 'https' else 80)
    gateway = context.gateway(allowed_urls=allowed_urls)

    async def switch():
        if not context.can_switch(host, port):
            return False
        # gateway.connect 使用同一目标锁，预先保留此次备用额度。
        context.attempted.add((host, port))
        generation = context.store.generation
        route, _ = context.select(host, port)
        alternative = 'direct' if route == 'proxy' else 'proxy'
        try:
            _, writer, _ = await gateway.connect(
                host, port, forced_route=alternative, timeout=timeout)
            writer.close()
            await writer.wait_closed()
        except (OSError, TimeoutError):
            return False
        context.stage_route(host, port, alternative, generation)
        return True

    return await _gateway_loop().wait(switch())


def _transport_kwargs(kwargs):
    return {key: kwargs[key] for key in ('verify', 'cert', 'http1', 'http2', 'limits')
            if key in kwargs}


def _retry_budget(request, started):
    values = [v for v in request.extensions.get('timeout', {}).values() if v is not None]
    return max(0, (max(values) if values else 60) - (time.monotonic() - started))


def _safe_method(request):
    return (request.method in {'GET', 'HEAD'}
            and request.headers.get('content-length', '0') == '0'
            and 'transfer-encoding' not in request.headers)


class _RoutedTransport(httpx.BaseTransport):
    def __init__(self, allowed_urls, safe_reads, kwargs):
        self.allowed_urls, self.safe_reads, self.kwargs = allowed_urls, safe_reads, kwargs
        self.transports = {}
        self.lock = threading.RLock()

    def handle_request(self, request):
        from . import current_context
        context = current_context()
        with self.lock:
            for key, (old, transport) in list(self.transports.items()):
                if old.drained:
                    self.transports.pop(key)
                    transport.close()
            if context not in self.transports:
                gateway = context.gateway(allowed_urls=self.allowed_urls)
                self.transports[context] = (context, httpx.HTTPTransport(
                    proxy=f'http://127.0.0.1:{gateway.port}', trust_env=False, **self.kwargs))
            transport = self.transports[context][1]
        started = time.monotonic()
        try:
            response = transport.handle_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout,
                httpx.RemoteProtocolError, httpx.ReadError) as exc:
            budget = _retry_budget(request, started)
            if (not self.safe_reads or not _safe_method(request) or budget <= 0
                    or _certificate_error(exc)):
                raise
            # 同步客户端也可能在事件循环线程内调用，因此使用独立 I/O loop。
            from . import _gateway_loop
            async def switch():
                return await _alternative(context, request.url, self.allowed_urls, budget)
            if not _gateway_loop().run(switch()):
                raise
            remaining = _retry_budget(request, started)
            if remaining <= 0:
                raise
            request.extensions['timeout'] = {
                k: min(v, remaining) if v is not None else remaining
                for k, v in request.extensions.get('timeout', {}).items()}
            response = transport.handle_request(request)
        context.confirm_url(str(request.url), response.status_code)
        return response

    def close(self):
        with self.lock:
            for _, transport in self.transports.values():
                transport.close()
            self.transports.clear()


class _AsyncRoutedTransport(httpx.AsyncBaseTransport):
    def __init__(self, allowed_urls, safe_reads, kwargs):
        self.allowed_urls, self.safe_reads, self.kwargs = allowed_urls, safe_reads, kwargs
        self.transports = {}

    async def handle_async_request(self, request):
        from . import current_context
        context = current_context()
        for key, (old, transport) in list(self.transports.items()):
            if old.drained:
                removed = self.transports.pop(key, None)
                if removed is not None:
                    await removed[1].aclose()
        if context not in self.transports:
            gateway = context.gateway(allowed_urls=self.allowed_urls)
            self.transports[context] = (context, httpx.AsyncHTTPTransport(
                proxy=f'http://127.0.0.1:{gateway.port}', trust_env=False, **self.kwargs))
        transport = self.transports[context][1]
        started = time.monotonic()
        try:
            response = await transport.handle_async_request(request)
        except (httpx.ConnectError, httpx.ConnectTimeout,
                httpx.RemoteProtocolError, httpx.ReadError) as exc:
            budget = _retry_budget(request, started)
            if (not self.safe_reads or not _safe_method(request) or budget <= 0
                    or _certificate_error(exc)
                    or not await _alternative(context, request.url, self.allowed_urls, budget)):
                raise
            remaining = _retry_budget(request, started)
            if remaining <= 0:
                raise
            request.extensions['timeout'] = {
                k: min(v, remaining) if v is not None else remaining
                for k, v in request.extensions.get('timeout', {}).items()}
            response = await transport.handle_async_request(request)
        context.confirm_url(str(request.url), response.status_code)
        return response

    async def aclose(self):
        closing = list(self.transports.values())
        self.transports.clear()
        for _, transport in closing:
            await transport.aclose()


def httpx_client(*, allowed_urls=(), safe_reads=True, client_class=httpx.Client, **kwargs):
    kwargs.pop('proxy', None)
    kwargs['trust_env'] = False
    kwargs.setdefault('transport', _RoutedTransport(
        tuple(allowed_urls), safe_reads, _transport_kwargs(kwargs)))
    return client_class(**kwargs)


def httpx_async_client(
    *, allowed_urls=(), safe_reads=True, client_class=httpx.AsyncClient, **kwargs,
):
    kwargs.pop('proxy', None)
    kwargs['trust_env'] = False
    kwargs.setdefault('transport', _AsyncRoutedTransport(
        tuple(allowed_urls), safe_reads, _transport_kwargs(kwargs)))
    return client_class(**kwargs)


def aiohttp_session(*, allowed_urls=(), safe_reads=True, **kwargs):
    import aiohttp

    from . import current_context, proxy_url
    context = current_context()

    async def feedback(request, handler):
        started = time.monotonic()
        try:
            response = await handler(request)
        except (aiohttp.ClientConnectorError,
                aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as exc:
            total = getattr(kwargs.get('timeout'), 'total', None) or 60
            remaining = total - (time.monotonic() - started)
            if (not safe_reads or not _safe_method(request) or remaining <= 0
                    or _certificate_error(exc)
                    or not await _alternative(context, request.url, allowed_urls, remaining)):
                raise
            response = await handler(request)
        context.confirm_url(str(response.url), response.status)
        return response

    kwargs['trust_env'] = False
    kwargs['proxy'] = proxy_url(allowed_urls=allowed_urls)
    kwargs['middlewares'] = (feedback, *kwargs.get('middlewares', ()))
    return aiohttp.ClientSession(**kwargs)
