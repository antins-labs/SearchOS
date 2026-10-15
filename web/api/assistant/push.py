from __future__ import annotations

import base64
import importlib.util
import json
import os
from urllib.parse import urlsplit

from .auth import Config


def validate_subscription(value: dict) -> dict:
    endpoint = value.get("endpoint", "")
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or "").lower()
    hosts = {"fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com", "web.push.apple.com"}
    # Extra enterprise push endpoints must be explicitly configured by the operator.
    hosts.update(item.strip().lower() for item in os.getenv("SF_PUSH_ALLOWED_HOSTS", "").split(",") if item.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment or parsed.port not in {None, 443} or not (host in hosts or host.endswith(".push.apple.com")):
        raise ValueError("不支持的推送服务地址")
    if len(endpoint) > 4096:
        raise ValueError("推送地址过长")
    keys = value.get("keys", {})
    for name, expected in (("p256dh", 65), ("auth", 16)):
        raw = keys.get(name, "")
        if not isinstance(raw, str) or len(raw) > 128:
            raise ValueError("无效的推送订阅密钥")
        try:
            decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        except Exception as exc:
            raise ValueError("无效的推送订阅密钥") from exc
        if len(decoded) != expected or (name == "p256dh" and decoded[0] != 4):
            raise ValueError("无效的推送订阅密钥")
    return {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


class PushSender:
    def __init__(self, config: Config):
        self.config = config
        self.key_path = config.root / "vapid-private.pem"
        self.public_key = ""
        self.reason = ""
        if not config.remote:
            self.reason = "需要先配置 HTTPS 访问入口"
        elif not config.push_contact.startswith("mailto:") or "@" not in config.push_contact:
            self.reason = "服务端尚未配置 SF_PUSH_CONTACT 联系邮箱"
        elif not importlib.util.find_spec("pywebpush"):
            self.reason = "服务端尚未安装 mobile 推送依赖"
        else:
            self._load_key()

    @property
    def ready(self):
        return bool(self.public_key)

    def _load_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        try:
            private = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        except FileNotFoundError:
            private = ec.generate_private_key(ec.SECP256R1())
            content = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            try:
                fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
            except FileExistsError:
                private = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        public = private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.public_key = base64.urlsafe_b64encode(public).rstrip(b"=").decode()

    def send(self, subscription: dict, notification: dict) -> str:
        """Return sent/gone; errors deliberately exclude subscription URLs and keys."""
        from pywebpush import WebPushException, webpush
        from requests import Session
        class NoRedirectSession(Session):
            def post(self, *args, **kwargs):
                kwargs["allow_redirects"] = False
                return super().post(*args, **kwargs)
        validate_subscription(subscription)
        payload = {"title": "SearchOS", "body": "你的任务已有结果，请打开查看。" if notification["kind"] == "completed" else "有一项任务需要你查看。", "url": notification["url"], "tag": notification["id"]}
        try:
            with NoRedirectSession() as session:
                response = webpush(subscription_info=subscription, data=json.dumps(payload), vapid_private_key=str(self.key_path), vapid_claims={"sub": self.config.push_contact}, timeout=10, ttl=86400, requests_session=session)
            if response.status_code in {404, 410}:
                return "gone"
            if response.status_code >= 300:
                raise RuntimeError(f"Push HTTP {response.status_code}")
            return "sent"
        except WebPushException as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in {404, 410}:
                return "gone"
            raise RuntimeError(f"Push HTTP {code or 'unavailable'}") from None
        except Exception:
            raise RuntimeError("Push transport unavailable") from None
