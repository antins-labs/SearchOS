"""Centralized LLM construction — driven by settings.profiles + settings.roles.

Usage::

    from searchos.config.models import get_model_for

    orchestrator = get_model_for("orchestrator")
    judge        = get_model_for("judge")

Roles are listed in ``settings.ROLE_NAMES``. Each role is bound to a profile
in ``settings.roles``; each profile spec lives in ``settings.profiles``.
Override at runtime via env vars, e.g. ``SF_ROLES__JUDGE=glm5-strong``.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult
from langchain_core.rate_limiters import BaseRateLimiter

from searchos.config.settings import ROLE_NAMES, ModelProfile, settings
from searchos.harness.telemetry.usage import TokenTrackingCallback, extract_token_usage
from searchos.network import httpx_async_client, httpx_client

_WINDOW_S = 60.0


class SlidingWindowRateLimiter(BaseRateLimiter):
    """RPM + TPM limiter over a trailing 60s window (0 disables a dimension).

    Thread-safe; the async path polls with ``asyncio.sleep``.
    """

    def __init__(
        self,
        rpm: int = 0,
        tpm: int = 0,
        check_every_s: float = 0.2,
    ) -> None:
        self.rpm = max(0, rpm)
        self.tpm = max(0, tpm)
        self._check_every_s = check_every_s
        self._lock = threading.Lock()
        self._requests: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()
        self._token_sum = 0  # running sum of _token_events, kept in sync

    def _evict(self, now: float) -> None:
        cutoff = now - _WINDOW_S
        while self._requests and self._requests[0] <= cutoff:
            self._requests.popleft()
        while self._token_events and self._token_events[0][0] <= cutoff:
            _, n = self._token_events.popleft()
            self._token_sum -= n

    def _try_acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if self.rpm and len(self._requests) >= self.rpm:
                return False
            if self.tpm and self._token_sum >= self.tpm:
                return False
            self._requests.append(now)
            return True

    def record_tokens(self, n: int) -> None:
        """Report actual token usage of a completed response (TPM feed)."""
        if n <= 0:
            return
        with self._lock:
            self._token_events.append((time.monotonic(), n))
            self._token_sum += n

    def set_limits(self, rpm: int, tpm: int) -> None:
        """Update this shared quota bucket without discarding window history."""
        with self._lock:
            self.rpm = max(0, rpm)
            self.tpm = max(0, tpm)

    # -- BaseRateLimiter interface --

    def acquire(self, *, blocking: bool = True) -> bool:
        if not blocking:
            return self._try_acquire()
        while not self._try_acquire():
            time.sleep(self._check_every_s)
        return True

    async def aacquire(self, *, blocking: bool = True) -> bool:
        if not blocking:
            return self._try_acquire()
        while not self._try_acquire():
            await asyncio.sleep(self._check_every_s)
        return True


class UsageReportingCallback(BaseCallbackHandler):
    """Feeds each response's actual token usage into the limiter's TPM window."""

    def __init__(self, limiter: SlidingWindowRateLimiter) -> None:
        self._limiter = limiter

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        _, _, total, _ = extract_token_usage(response)
        self._limiter.record_tokens(total)


# One (limiter, callback) per bucket; later registrations refresh rpm/tpm.
_registry: dict[tuple[str, str, str], tuple[SlidingWindowRateLimiter, UsageReportingCallback]] = {}
_registry_lock = threading.Lock()


def get_shared_rate_limiter(
    key: tuple[str, str, str],
    rpm: int,
    tpm: int,
) -> tuple[SlidingWindowRateLimiter, UsageReportingCallback]:
    """Process-wide limiter for a quota bucket ``(api_base, model, api_key_env)``."""
    with _registry_lock:
        entry = _registry.get(key)
        if entry is None:
            limiter = SlidingWindowRateLimiter(rpm=rpm, tpm=tpm)
            entry = (limiter, UsageReportingCallback(limiter))
            _registry[key] = entry
        else:
            entry[0].set_limits(rpm, tpm)
        return entry


def _patch_reasoning_content() -> None:
    """Preserve ``reasoning_content`` (GLM-5 / DeepSeek-R1 / QwQ) into
    AIMessage.additional_kwargs — langchain-openai 1.x drops it.
    Ref: https://github.com/langchain-ai/langchain/issues/35059
    """
    import langchain_openai.chat_models.base as _base
    from langchain_core.messages import AIMessage

    _original_ccr = _base.ChatOpenAI._create_chat_result

    def _patched_ccr(
        self: _base.ChatOpenAI,
        response: Any,
        generation_info: dict | None = None,
    ) -> Any:
        result = _original_ccr(self, response, generation_info)
        if not isinstance(response, dict):
            choices = getattr(response, "choices", None) or []
            for i, choice in enumerate(choices):
                msg = getattr(choice, "message", None)
                if msg is None:
                    continue
                extras = getattr(msg, "model_extra", None) or {}
                rc = extras.get("reasoning_content", "")
                if rc and i < len(result.generations):
                    gen_msg = result.generations[i].message
                    if isinstance(gen_msg, AIMessage):
                        gen_msg.additional_kwargs["reasoning_content"] = rc
        return result

    if not getattr(_base, "_sf_reasoning_patched", False):
        _base.ChatOpenAI._create_chat_result = _patched_ccr
        _base._sf_reasoning_patched = True  # type: ignore[attr-defined]


_patch_reasoning_content()


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_profile(role: str) -> ModelProfile:
    """Look up the ModelProfile bound to a role. Raises on misconfiguration."""
    if role not in ROLE_NAMES:
        raise ValueError(
            f"Unknown role {role!r}. Known roles: {ROLE_NAMES}"
        )
    profile_name = settings.roles.get(role)
    if not profile_name:
        raise ValueError(
            f"Role {role!r} has no profile binding in settings.roles. "
            f"Set settings.roles[{role!r}] to one of: {list(settings.profiles)}"
        )
    profile = settings.profiles.get(profile_name)
    if profile is None:
        raise ValueError(
            f"Role {role!r} → profile {profile_name!r} not in settings.profiles. "
            f"Available: {list(settings.profiles)}"
        )
    return profile


def _rate_limit_kwargs(profile: ModelProfile) -> dict[str, Any]:
    """Shared limiter + usage callback for the profile's quota bucket."""
    limiter, usage_cb = get_shared_rate_limiter(
        (profile.api_base, profile.model, profile.api_key_env),
        rpm=profile.rpm, tpm=profile.tpm,
    )
    if not (profile.rpm or profile.tpm):
        return {}
    return {"rate_limiter": limiter, "callbacks": [usage_cb]}


def get_model_for(
    role: str,
    *,
    model_override: str | None = None,
) -> BaseChatModel:
    """Build a fresh BaseChatModel for the role.

    ``model_override`` changes only the wire model id while retaining the
    role's configured provider, endpoint, key env, protocol, and limits. It is
    intended for narrow CLI overrides; normal runtime calls should omit it.
    """
    profile = resolve_profile(role)
    if model_override:
        profile = profile.model_copy(update={"model": model_override})
    # api_key_fallback covers local servers (Ollama/vLLM) that need a
    # placeholder key even without auth.
    api_key = os.environ.get(profile.api_key_env, "") or profile.api_key_fallback
    if not api_key:
        # Fail loud — a silent empty key produces cryptic deep 401s.
        raise RuntimeError(
            f"Role {role!r} → profile uses api_key_env={profile.api_key_env!r}, "
            f"but that env var is not set. Add it to your .env file "
            f"(quick start: SF_PROVIDER + key, see searchos/config/providers.py)."
        )

    rl_kwargs = _rate_limit_kwargs(profile)
    callbacks = [TokenTrackingCallback(role=role), *rl_kwargs.pop("callbacks", [])]

    if profile.provider in ("openai_compatible", "openai"):
        from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

        kwargs: dict[str, Any] = {
            "model": profile.model,
            "api_key": api_key,
            "max_tokens": profile.max_tokens,
            "max_retries": settings.llm_max_retries,
            "callbacks": callbacks,
            "stream_usage": True,
            **rl_kwargs,
        }
        if profile.temperature is not None:
            kwargs["temperature"] = profile.temperature
        if profile.api_base:
            kwargs["base_url"] = profile.api_base
        # How the thinking switch is spelled differs per gateway; strict APIs
        # (OpenAI/Gemini/OpenRouter) reject unknown params, so "none" sends
        # nothing at all.
        extra_body: dict[str, Any] = {}
        if profile.thinking_style == "chat_template_kwargs":
            # vLLM / SiliconFlow 系网关只认 chat_template_kwargs 里的开关；
            # 顶层形式会被静默忽略。
            extra_body["chat_template_kwargs"] = {
                "enable_thinking": bool(profile.enable_thinking),
            }
        elif profile.thinking_style == "enable_thinking":
            # DashScope compatible-mode top-level switch.
            extra_body["enable_thinking"] = bool(profile.enable_thinking)
        # Deep-merge profile extra_body so it doesn't clobber the whole dict.
        profile_extra = dict(profile.extra)
        profile_extra_body = profile_extra.pop("extra_body", None)
        if isinstance(profile_extra_body, dict):
            for k, v in profile_extra_body.items():
                if isinstance(v, dict) and isinstance(extra_body.get(k), dict):
                    extra_body[k] = {**extra_body[k], **v}
                else:
                    extra_body[k] = v
        if extra_body:
            kwargs["extra_body"] = extra_body
        kwargs.update(profile_extra)
        # 客户端显式绑定任务网络；保留 SDK 的超时、连接池与重试默认值。
        from openai import DEFAULT_CONNECTION_LIMITS, DefaultAsyncHttpxClient, DefaultHttpxClient

        allowed_urls = (str(kwargs.get("base_url") or kwargs.get("openai_api_base")
                            or os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
                            or "https://api.openai.com/v1"),)
        kwargs["http_client"] = httpx_client(
            client_class=DefaultHttpxClient, allowed_urls=allowed_urls, safe_reads=False,
            limits=DEFAULT_CONNECTION_LIMITS,
        )
        kwargs["http_async_client"] = httpx_async_client(
            client_class=DefaultAsyncHttpxClient, allowed_urls=allowed_urls, safe_reads=False,
            limits=DEFAULT_CONNECTION_LIMITS,
        )
        kwargs.pop("openai_proxy", None)
        client = UsagePreservingChatOpenAI(**kwargs)

    elif profile.provider == "anthropic":
        # Lazy import — anthropic is optional.
        from searchos.harness.telemetry.usage import UsagePreservingChatAnthropic

        kwargs = {
            "model": profile.model,
            "api_key": api_key,
            "max_tokens": profile.max_tokens,
            "max_retries": settings.llm_max_retries,
            "callbacks": callbacks,
            **rl_kwargs,
        }
        if profile.temperature is not None:
            kwargs["temperature"] = profile.temperature
        # Custom Anthropic-compatible gateway — pass base_url so the
        # SDK routes to the override instead of api.anthropic.com.
        if profile.api_base:
            kwargs["base_url"] = profile.api_base
        kwargs.update(profile.extra)
        from anthropic import DEFAULT_CONNECTION_LIMITS, DefaultAsyncHttpxClient, DefaultHttpxClient

        allowed_urls = (str(kwargs.get("base_url") or kwargs.get("anthropic_api_url")
                            or os.getenv("ANTHROPIC_API_URL") or os.getenv("ANTHROPIC_BASE_URL")
                            or "https://api.anthropic.com"),)
        kwargs["http_client"] = httpx_client(
            client_class=DefaultHttpxClient, allowed_urls=allowed_urls, safe_reads=False,
            limits=DEFAULT_CONNECTION_LIMITS,
        )
        kwargs["http_async_client"] = httpx_async_client(
            client_class=DefaultAsyncHttpxClient, allowed_urls=allowed_urls, safe_reads=False,
            limits=DEFAULT_CONNECTION_LIMITS,
        )
        kwargs.pop("anthropic_proxy", None)
        client = UsagePreservingChatAnthropic(**kwargs)
    else:
        raise ValueError(f"Unsupported provider: {profile.provider!r}")

    if profile.input_budget is not None:
        client.profile = {**(client.profile or {}), "max_input_tokens": profile.input_budget}
    return client


__all__ = ["get_model_for", "resolve_profile"]
