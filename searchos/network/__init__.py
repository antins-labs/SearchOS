"""SearchOS 宿主网络入口；任务共享配置，连接独立执行权限检查。"""
from __future__ import annotations

import asyncio
import atexit
import os
import ssl
import threading
import time
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from .config import NetworkConfig, RouteStore

_configuration: NetworkConfig | None = None
_store = RouteStore()
_active: ContextVar[NetworkContext | None] = ContextVar('searchos_network', default=None)
_default_context = None
_global_lock = threading.RLock()
_contexts = weakref.WeakSet()


class _GatewayLoop:
    """同步 SDK 和异步调用共同使用独立的 I/O 线程。"""
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self.loop.run_forever, name='searchos-network', daemon=True)
        self.thread.start()

    def run(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout=30)

    async def wait(self, coroutine):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coroutine, self.loop))


_io = None


def _gateway_loop():
    global _io
    with _global_lock:
        if _io is None:
            _io = _GatewayLoop()
        return _io


class NetworkContext:
    def __init__(self, config: NetworkConfig | None = None, *, store=None):
        self.config = config or network_settings()
        self.store = store if store is not None else _store
        self._route_generation = self.store.generation
        self.pending: dict[tuple[str, int], str] = {}
        self.validation_routes: set[tuple[str, int]] = set()
        self.attempted: set[tuple[str, int]] = set()
        self.connection_locks = {}
        self._gateways = {}
        self._events = []
        self._lock = threading.RLock()
        self.closed = False
        _contexts.add(self)

    @property
    def events(self):
        with self._lock:
            return [dict(event) for event in self._events]

    @property
    def event_cursor(self):
        with self._lock:
            return len(self._events)

    @property
    def drained(self):
        with self._lock:
            return self.closed and not self._gateways

    def events_since(self, cursor):
        with self._lock:
            return [dict(event) for event in self._events[cursor:]]

    def record(self, host, port, route, source, phase, elapsed):
        with self._lock:
            self._events.append({'sequence': len(self._events) + 1,
                'host': host, 'port': port, 'route': route, 'source': source,
                'phase': phase, 'ok': phase == 'connected', 'latency_ms': round(elapsed * 1000, 2),
                'config_fingerprint': self.config.fingerprint})

    def select(self, host, port):
        self._sync_routes()
        if route := self.config.manual_route(host):
            return route, 'manual'
        with self._lock:
            if route := self.pending.get((host, port)):
                return route, 'task'
        if self.config.auto_route:
            if route := self.store.get(self.config, host, port):
                return route, 'learned'
        return ('proxy' if self.config.proxy_url else 'direct'), 'default'

    def can_switch(self, host, port):
        self._sync_routes()
        return (self.config.auto_route and bool(self.config.proxy_url)
                and not self.config.manual_route(host) and (host, port) not in self.attempted)

    def _sync_routes(self):
        with self._lock:
            if self._route_generation != self.store.generation:
                self.pending.clear()
                self.validation_routes.clear()
                self.attempted.clear()
                self._route_generation = self.store.generation

    def stage_route(self, host, port, route, generation, *, require_validation=False):
        with self._lock:
            self._sync_routes()
            if generation == self._route_generation:
                self.pending[host, port] = route
                if require_validation:
                    self.validation_routes.add((host, port))
                return True
            return False

    def confirm_url(self, url, status=200):
        self._sync_routes()
        if not 200 <= status < 400:
            return
        try:
            value = urlsplit(str(url))
            key = ((value.hostname or '').lower().rstrip('.'),
                   value.port or (443 if value.scheme == 'https' else 80))
        except ValueError:
            return
        with self._lock:
            route = self.pending.get(key)
            if route and key not in self.validation_routes:
                self.store.put(self.config, *key, route, generation=self._route_generation)

    def confirm_connections(self, executions):
        """保存业务验收引用的执行线路，排除诊断、旧配置和已清除的记录。"""
        with self._lock:
            self._sync_routes()
            if not self.config.auto_route:
                return
            for network in executions:
                if (network.get('config_fingerprint') != self.config.fingerprint
                        or network.get('route_generation') != self._route_generation):
                    continue
                for connection in network.get('connections', []):
                    host, port, route = (connection['host'], connection['port'], connection['route'])
                    if (connection.get('phase') != 'connected' or connection.get('source') == 'diagnostic'
                            or connection.get('config_fingerprint') != self.config.fingerprint
                            or self.config.manual_route(host)):
                        continue
                    self.store.put(self.config, host, port, route, generation=self._route_generation)
                    if self.pending.get((host, port)) == route:
                        self.validation_routes.discard((host, port))

    def gateway(self, *, policy=None, allowed_urls=()):
        from .gateway import DestinationPolicy, NetworkProxy
        key = (('policy', id(policy)) if policy is not None
               else ('origins', tuple(sorted(allowed_urls))))
        with self._lock:
            if self.closed:
                raise RuntimeError('network context has closed')
            if key not in self._gateways:
                proxy = NetworkProxy(policy or DestinationPolicy(allowed_urls), context=self)
                _gateway_loop().run(proxy.start())
                self._gateways[key] = proxy
            return self._gateways[key]

    def close(self):
        with self._lock:
            if self.closed and not self._gateways:
                return
            self.closed = True
            gateways = list(self._gateways.values())
            self._gateways.clear()
        if gateways:
            async def close_all():
                await asyncio.gather(*(gateway.close() for gateway in gateways))
            _gateway_loop().run(close_all())

    def retire(self):
        """配置更新后停止接收新连接，等待已有连接自然结束。"""
        with self._lock:
            self.closed = True
            gateways = list(self._gateways.values())
        if not gateways:
            return

        async def drain():
            for gateway in gateways:
                gateway.server.close()
                await gateway.server.wait_closed()
            running = [task for gateway in gateways for task in gateway.connections]
            if running:
                await asyncio.gather(*running, return_exceptions=True)
            for gateway in gateways:
                await gateway.close()
            with self._lock:
                self._gateways.clear()

        _gateway_loop().loop.call_soon_threadsafe(lambda: asyncio.create_task(drain()))


def network_settings() -> NetworkConfig:
    global _configuration
    with _global_lock:
        if _configuration is None:
            proxy = next((os.environ.get(key.upper()) or os.environ.get(key)
                          for key in ('https_proxy', 'http_proxy', 'all_proxy')
                          if os.environ.get(key.upper()) or os.environ.get(key)), '')
            _configuration = NetworkConfig(
                proxy_url=proxy, source='environment' if proxy else 'default')
        return _configuration


def configure(config: NetworkConfig | dict, *, cache_path: Path | None = None):
    global _configuration, _store, _default_context
    parsed = config if isinstance(config, NetworkConfig) else NetworkConfig(**config)
    retired = None
    with _global_lock:
        unchanged = (_configuration is not None and _configuration.fingerprint == parsed.fingerprint
                     and (cache_path is None or _store.path == Path(cache_path)))
        _configuration = parsed
        if cache_path is not None and _store.path != Path(cache_path):
            _store = RouteStore(Path(cache_path))
        # 已有任务保留快照；后续非任务调用建立新入口。
        if not unchanged:
            retired = _default_context
            _default_context = None
    if retired is not None:
        retired.retire()
    return parsed


def active_context():
    return _active.get()


def current_context() -> NetworkContext:
    global _default_context
    if context := _active.get():
        return context
    with _global_lock:
        if _default_context is None or _default_context.closed:
            _default_context = NetworkContext()
        return _default_context


@contextmanager
def network_context(config: NetworkConfig | dict | None = None, *, reuse=True):
    existing = active_context()
    if existing is not None and config is None and reuse:
        yield existing
        return
    if isinstance(config, dict):
        config = NetworkConfig(**config)
    context = NetworkContext(config)
    token = _active.set(context)
    try:
        yield context
    finally:
        _active.reset(token)
        context.close()


def network_scoped(function):
    """独立调用建立任务上下文，嵌套调用复用已有配置和线路。"""
    @wraps(function)
    async def invoke(*args, **kwargs):
        with network_context():
            return await function(*args, **kwargs)
    return invoke


def proxy_url(*, policy=None, allowed_urls=()):
    gateway = current_context().gateway(policy=policy, allowed_urls=allowed_urls)
    return f'http://127.0.0.1:{gateway.port}'


def proxy_environment(*, policy=None, allowed_urls=()):
    endpoint = proxy_url(policy=policy, allowed_urls=allowed_urls)
    env = {key: endpoint for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                                    'http_proxy', 'https_proxy', 'all_proxy')}
    env.update(NO_PROXY='localhost,127.0.0.1,::1', no_proxy='localhost,127.0.0.1,::1')
    return env


def learned_routes():
    return _store.list(network_settings())


def clear_learned_routes(host=None):
    _store.clear(host)


async def network_check(url: str, route: str | None = None):
    """探测连接；可为创建任务暂选线路，业务验收后由宿主保存。"""
    value = urlsplit(url)
    if (value.scheme not in {'http', 'https'} or not value.hostname
            or value.username or value.password):
        raise ValueError('diagnostic URL must be a public HTTP(S) URL')
    context = current_context()
    host, port = (value.hostname.lower().rstrip('.'),
                  value.port or (443 if value.scheme == 'https' else 80))
    current, source = context.select(host, port)
    if route is not None:
        if route not in {'direct', 'proxy'}:
            raise ValueError('route must be direct or proxy')
        if not context.config.auto_route:
            raise ValueError('automatic route selection is disabled')
        if route == 'proxy' and not context.config.proxy_url:
            raise ValueError('proxy route requires a configured proxy')
        if manual := context.config.manual_route(host):
            if manual != route:
                raise ValueError('target route is fixed by a manual rule')
    routes = [route] if route is not None else [current] + (
        [('direct' if current == 'proxy' else 'proxy')]
        if context.config.proxy_url and not context.config.manual_route(host) else [])
    gateway = context.gateway()

    async def check():
        generation = context.store.generation
        attempts = []
        selected = False
        for candidate in routes:
            started = time.monotonic()
            writer = None
            try:
                async with asyncio.timeout(7.5):
                    _, writer, _ = await gateway.connect(
                        host, port, forced_route=candidate, timeout=7.5)
                    if value.scheme == 'https':
                        await writer.start_tls(ssl.create_default_context(), server_hostname=host)
                result = {'route': candidate, 'ok': True, 'phase': 'connected'}
            except (OSError, TimeoutError) as exc:
                phase = ('tls_certificate' if isinstance(exc, ssl.SSLCertVerificationError)
                         else getattr(exc, 'phase',
                                      'tls_handshake' if writer else 'target_connect'))
                result = {'route': candidate, 'ok': False, 'phase': phase}
            finally:
                if writer:
                    writer.close()
                    try:
                        async with asyncio.timeout(1):
                            await writer.wait_closed()
                    except (OSError, TimeoutError):
                        pass
                    finally:
                        writer.transport.abort()
            result['latency_ms'] = round((time.monotonic() - started) * 1000, 2)
            attempts.append(result)
            if result['phase'] in {'destination_denied', 'tls_certificate', 'proxy_auth'}:
                break
        if route is not None and attempts[0]['ok']:
            selected = context.stage_route(host, port, route, generation, require_validation=True)
            if selected:
                context.attempted.add((host, port))
        elif (context.config.auto_route and not attempts[0]['ok'] and len(attempts) > 1
                and attempts[1]['ok'] and context.can_switch(host, port)):
            context.attempted.add((host, port))
            context.stage_route(host, port, attempts[1]['route'], generation)
        result = {'ok': any(a['ok'] for a in attempts), 'host': host, 'port': port,
                'route': current, 'source': source, 'attempts': attempts,
                'config_fingerprint': context.config.fingerprint, 'verified': 'connection_only'}
        if route is not None:
            result['selected_route'] = route if selected else None
        return result

    return await _gateway_loop().wait(check())


def shutdown():
    global _default_context, _io
    for context in list(_contexts):
        context.close()
    _default_context = None
    if _io:
        _io.loop.call_soon_threadsafe(_io.loop.stop)
        _io.thread.join(timeout=2)
        _io = None


atexit.register(shutdown)

from .clients import aiohttp_session, httpx_async_client, httpx_client  # noqa: E402

__all__ = ['NetworkConfig', 'NetworkContext', 'configure', 'network_settings', 'network_context',
           'network_scoped',
           'current_context', 'active_context', 'proxy_url', 'proxy_environment', 'network_check',
           'learned_routes', 'clear_learned_routes', 'aiohttp_session',
           'httpx_client', 'httpx_async_client']
