"""宿主网络设置与只含连接元数据的线路记录。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)


def public_proxy(value: str) -> str:
    if not value:
        return ''
    parsed = urlsplit(value)
    host = parsed.hostname or ''
    if ':' in host:
        host = f'[{host}]'
    return urlunsplit((parsed.scheme, host + (f':{parsed.port}' if parsed.port else ''),
                       '', '', ''))


@dataclass(frozen=True)
class NetworkConfig:
    proxy_url: str = field(default='', repr=False)
    auto_route: bool = True
    routes: dict[str, str] = field(default_factory=dict)
    source: str = 'settings'

    def __post_init__(self):
        if self.proxy_url:
            parsed = urlsplit(self.proxy_url)
            if (parsed.scheme not in {'http', 'https', 'socks5', 'socks5h'}
                    or not parsed.hostname or parsed.path not in ('', '/')
                    or parsed.query or parsed.fragment):
                raise ValueError('proxy must be an HTTP, HTTPS or SOCKS5 endpoint')
            _ = parsed.port
        routes = {}
        for domain, route in self.routes.items():
            domain = domain.lower().strip().rstrip('.')
            if not domain or any(c in domain for c in '/@ :') or route not in {'direct', 'proxy'}:
                raise ValueError('route requires a hostname and direct/proxy')
            if route == 'proxy' and not self.proxy_url:
                raise ValueError('proxy route requires a configured proxy')
            routes[domain] = route
        object.__setattr__(self, 'routes', MappingProxyType(routes))

    @property
    def proxy_fingerprint(self) -> str:
        return hashlib.sha256(self.proxy_url.encode()).hexdigest()[:24]

    @property
    def fingerprint(self) -> str:
        value = [self.proxy_url, self.auto_route, sorted(self.routes.items())]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()[:24]

    def snapshot(self) -> dict:
        return {'proxy_url': public_proxy(self.proxy_url), 'auto_route': self.auto_route,
                'routes': dict(self.routes), 'source': self.source, 'fingerprint': self.fingerprint}

    def manual_route(self, host: str) -> str | None:
        host = host.lower().rstrip('.')
        matches = [domain for domain in self.routes
                   if host == domain or host.endswith('.' + domain)]
        return self.routes[max(matches, key=len)] if matches else None


class RouteStore:
    """每个代理配置独立缓存，写入原子替换；不保存请求内容。"""
    ttl = 86400

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.lock = threading.RLock()
        self.rows: dict[str, dict] = {}
        self.generation = 0
        self._load()

    def _load(self):
        if self.path:
            try:
                data = json.loads(self.path.read_text())
                self.rows = {r['key']: r for r in data.get('routes', [])
                             if isinstance(r, dict) and r.get('expires_at', 0) > time.time()
                             and r.get('route') in {'direct', 'proxy'}
                             and isinstance(r.get('key'), str)
                             and isinstance(r.get('proxy_fingerprint'), str)
                             and isinstance(r.get('host'), str) and isinstance(r.get('port'), int)}
            except (OSError, ValueError, TypeError, KeyError):
                self.rows = {}

    def _save(self):
        if not self.path:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.routes-', dir=self.path.parent)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'routes': list(self.rows.values())[-2048:]}, stream)
            os.replace(temporary, self.path)
        except OSError:
            logger.warning('Network route cache could not be saved; current task keeps its route')
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, config: NetworkConfig, host: str, port: int) -> str | None:
        with self.lock:
            row = self.rows.get(f'{config.proxy_fingerprint}/{host}:{port}')
            return row['route'] if row and row['expires_at'] > time.time() else None

    def put(self, config: NetworkConfig, host: str, port: int, route: str, *, generation=None):
        with self.lock:
            if generation is not None and generation != self.generation:
                return
            key = f'{config.proxy_fingerprint}/{host}:{port}'
            now = time.time()
            self.rows = {k: v for k, v in self.rows.items() if v['expires_at'] > now}
            self.rows[key] = {'key': key, 'host': host, 'port': port, 'route': route,
                              'verified_at': now, 'expires_at': now + self.ttl,
                              'proxy_fingerprint': config.proxy_fingerprint}
            self._save()

    def list(self, config: NetworkConfig) -> list[dict]:
        with self.lock:
            return [{k: v for k, v in row.items() if k not in {'key', 'proxy_fingerprint'}}
                    for row in self.rows.values() if row['expires_at'] > time.time()
                    and row['proxy_fingerprint'] == config.proxy_fingerprint]

    def clear(self, host: str | None = None):
        with self.lock:
            self.generation += 1
            self.rows = {k: v for k, v in self.rows.items() if host and v['host'] != host}
            self._save()
