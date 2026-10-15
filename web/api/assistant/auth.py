from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import secrets
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from .store import Store

COOKIE = "searchos_device"
PUBLIC_PATHS = {"/api/health", "/api/assistant/access", "/api/assistant/pairings/claim", "/api/assistant/login"}
LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Config:
    root: Path
    public_origin: str = ""
    push_contact: str = ""

    @classmethod
    def from_env(cls):
        root = Path(os.getenv("SF_ASSISTANT_ROOT", str(Path(__file__).resolve().parents[3] / ".searchos" / "assistant")))
        origin = os.getenv("SF_PUBLIC_ORIGIN", "").rstrip("/")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("SF_PUBLIC_ORIGIN must be a bare HTTPS origin, e.g. https://search.example.com")
        return cls(root, origin, os.getenv("SF_PUSH_CONTACT", ""))

    @property
    def remote(self):
        return bool(self.public_origin)


def ensure_admin_secret(config: Config) -> Path:
    path = config.root / "admin-token"
    config.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_urlsafe(36))
    return path


def loopback(host: str) -> bool:
    if host == "testclient":  # Starlette's in-process ASGI transport; never a network peer.
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def headers(scope):
    return {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}


def principal(scope, config: Config, store: Store):
    now = time.time()
    h = headers(scope)
    if not config.remote:
        peer = scope.get("client", ("", 0))[0]
        forwarded = h.get("x-forwarded-host", h.get("host", ""))
        try:
            host = urlsplit("http://" + forwarded).hostname
        except ValueError:
            return None
        if loopback(peer) and host in {"localhost", "127.0.0.1", "::1", "testserver"}:
            return {"id": "local", "name": "本机浏览器", "admin": True}
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(h.get("cookie", ""))
    except Exception:
        return None
    token = cookie.get(COOKIE)
    if not token:
        return None
    row = store.one("SELECT id,name,admin,last_seen FROM devices WHERE token_hash=? AND revoked IS NULL AND expires>?", (digest(token.value), now))
    if row and now - row["last_seen"] > 60:
        store.execute("UPDATE devices SET last_seen=? WHERE id=?", (now, row["id"]))
    return row


class AccessMiddleware:
    """Guard every API and socket, including existing search/settings/file routes."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"} or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        from .runtime import get_runtime
        service = get_runtime()
        config, store = service.config, service.store
        h = headers(scope)
        origin = h.get("origin")
        if origin and not (origin == config.public_origin if config.remote else LOCAL_ORIGIN.fullmatch(origin)):
            return await self.reject(scope, receive, send, 403, "访问来源不受信任")
        who = principal(scope, config, store)
        public = scope["path"] in PUBLIC_PATHS
        if not public and not who:
            return await self.reject(scope, receive, send, 401, "请先绑定设备")
        if config.remote and scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            if origin != config.public_origin or h.get("x-searchos-request") != "1":
                return await self.reject(scope, receive, send, 403, "请求缺少同源验证")
        if scope["type"] == "websocket" and config.remote and origin != config.public_origin:
            return await self.reject(scope, receive, send, 403, "WebSocket 来源不受信任")
        scope.setdefault("state", {})["assistant_device"] = who
        if scope["type"] == "http":
            async def private_send(message):
                if message["type"] == "http.response.start":
                    # Uploaded HTML must not execute with authenticated app authority.
                    extra = [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"), (b"content-security-policy", b"sandbox; frame-ancestors 'self'")]
                    names = {key for key, _ in extra}
                    message["headers"] = [(key, value) for key, value in message.get("headers", []) if key.lower() not in names] + extra
                await send(message)
            return await self.app(scope, receive, private_send)
        if not config.remote:
            return await self.app(scope, receive, send)
        # Revocation also closes already-open connections, not only new handshakes.
        async def watch_revocation():
            while True:
                await asyncio.sleep(1)
                if not principal(scope, config, store):
                    return
        app_task = asyncio.create_task(self.app(scope, receive, send))
        guard = asyncio.create_task(watch_revocation())
        try:
            done, _ = await asyncio.wait({app_task, guard}, return_when=asyncio.FIRST_COMPLETED)
            if guard in done:
                await send({"type": "websocket.close", "code": 1008})
                app_task.cancel()
            else:
                await app_task
        except WebSocketDisconnect:
            pass
        finally:
            guard.cancel()
            if not app_task.done():
                app_task.cancel()
            await asyncio.gather(guard, app_task, return_exceptions=True)

    @staticmethod
    async def reject(scope, receive, send, code, detail):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, send)
