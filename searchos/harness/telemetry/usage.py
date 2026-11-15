"""通用 API Usage 计量及 SDK、框架接入适配。"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import threading
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from inspect import isawaitable
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from pydantic import Field

logger = logging.getLogger(__name__)

MAIN_LOOP_ROLES = frozenset({"orchestrator", "sub_agent", "synthesis"})
_ROLE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "cached_prompt_tokens",
    "llm_calls",
    "cache_hit_calls",
    "cache_unreported_calls",
    "usage_unreported_calls",
    "usage_recording_errors",
)


_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_prompt_tokens")

_API_USAGE_KEYS = _FIELDS + (
    "input_tokens",
    "output_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "prompt_tokens_details",
    "input_tokens_details",
    "input_token_details",
)


def _usage_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_unset=True)
    keys = _API_USAGE_KEYS + (
        "usage",
        "token_usage",
        "response",
        "message",
        "type",
        "object",
        "protocol",
        "event",
    )
    attributes = {key: getattr(value, key) for key in keys if hasattr(value, key)}
    return attributes or None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
        return result if result >= 0 and result == float(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _first(data: Mapping, *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        value: Any = data
        for key in path:
            value = _usage_dict(value)
            value = value.get(key) if value is not None else None
        parsed = _integer(value)
        if parsed is not None:
            return parsed
    return None


def _parse(data: dict, protocol: str = "") -> dict[str, int | None]:
    prompt = _first(data, ("prompt_tokens",), ("input_tokens",))
    completion = _first(data, ("completion_tokens",), ("output_tokens",))
    cached = _first(
        data,
        ("cached_prompt_tokens",),
        ("prompt_tokens_details", "cached_tokens"),
        ("input_tokens_details", "cached_tokens"),
        ("input_token_details", "cache_read"),
        ("prompt_cache_hit_tokens",),
        ("cache_read_input_tokens",),
    )
    # Messages 的基础输入数还需计入缓存读取和缓存写入。
    if prompt is not None and protocol in {"messages", "anthropic"}:
        prompt += _integer(data.get("cache_read_input_tokens")) or 0
        prompt += _integer(data.get("cache_creation_input_tokens")) or 0
    return dict(zip(_FIELDS, (prompt, completion, _first(data, ("total_tokens",)), cached)))


@dataclass
class _UsageDetails:
    counts: dict[str, int | None] = field(default_factory=lambda: dict.fromkeys(_FIELDS))
    sources: dict[str, str] = field(default_factory=dict)
    raw: list[dict[str, Any]] = field(default_factory=list)
    normalized: list[dict[str, Any]] = field(default_factory=list)
    incomplete_fields: set[str] = field(default_factory=set)

    def fill(self, other: _UsageDetails, *, fields: tuple[str, ...] = _FIELDS) -> None:
        for key in fields:
            value = other.counts[key]
            if self.counts[key] is None and value is not None:
                self.counts[key] = value
                self.sources[key] = other.sources[key]
                if key in other.incomplete_fields:
                    self.incomplete_fields.add(key)

    def derive(self, *, cache: bool = True) -> None:
        prompt, completion, total, _ = (self.counts[k] for k in _FIELDS)
        if total is None and prompt is not None and completion is not None:
            self.counts["total_tokens"] = prompt + completion
            self.sources["total_tokens"] = "derived:prompt_tokens+completion_tokens"
            if self.incomplete_fields.intersection(("prompt_tokens", "completion_tokens")):
                self.incomplete_fields.add("total_tokens")
        elif (
            prompt is None and total is not None and completion is not None and total >= completion
        ):
            self.counts["prompt_tokens"] = total - completion
            self.sources["prompt_tokens"] = "derived:total_tokens-completion_tokens"
            if self.incomplete_fields.intersection(("total_tokens", "completion_tokens")):
                self.incomplete_fields.add("prompt_tokens")
        elif completion is None and total is not None and prompt is not None and total >= prompt:
            self.counts["completion_tokens"] = total - prompt
            self.sources["completion_tokens"] = "derived:total_tokens-prompt_tokens"
            if self.incomplete_fields.intersection(("total_tokens", "prompt_tokens")):
                self.incomplete_fields.add("completion_tokens")
        if (
            cache
            and self.counts["cached_prompt_tokens"] is None
            and self.counts["prompt_tokens"] is not None
            and "prompt_tokens" not in self.incomplete_fields
        ):
            for snapshot in reversed(self.raw):
                missed = _first(snapshot["usage"], ("prompt_cache_miss_tokens",))
                if missed is not None:
                    if self.counts["prompt_tokens"] >= missed:
                        self.counts["cached_prompt_tokens"] = self.counts["prompt_tokens"] - missed
                        self.sources["cached_prompt_tokens"] = (
                            f"derived:{snapshot['source']}:prompt_tokens-prompt_cache_miss_tokens"
                        )
                    break

    @property
    def values(self) -> tuple[int, int, int, int]:
        return tuple(self.counts[key] or 0 for key in _FIELDS)


def _snapshots(value: Any, source: str) -> list[dict[str, Any]]:
    snapshots = value if isinstance(value, list) else [value]
    result = []
    for index, entry in enumerate(snapshots):
        data = _usage_dict(entry)
        if data is None:
            continue
        envelope = _usage_dict(data.get("usage"))
        result.append(
            {
                "source": (data.get("source") if envelope is not None else None)
                or (f"{source}[{index}]" if isinstance(value, list) else source),
                "usage": envelope if envelope is not None else data,
                **(
                    {k: data[k] for k in ("event", "protocol") if k in data}
                    if envelope is not None
                    else {}
                ),
            }
        )
    return result


def _api_protocol(data: dict[str, Any]) -> str:
    event = str(data.get("type") or "")
    kind = str(data.get("object") or "")
    if event in {"message", "message_start", "message_delta", "message_stop"}:
        return "messages"
    if event.startswith("response.") or kind == "response":
        return "responses"
    if kind.startswith("chat.completion"):
        return "chat_completions"
    return ""


def _api_snapshots(
    value: Any,
    source: str = "response",
    *,
    protocol: str = "",
) -> list[dict[str, Any]]:
    """只提取 API 的 Usage，排除回答正文与其他响应内容。"""
    if isinstance(value, (list, tuple)):
        return [
            snapshot
            for index, event in enumerate(value)
            for snapshot in _api_snapshots(event, f"{source}[{index}]", protocol=protocol)
        ]
    data = _usage_dict(value)
    if data is None:
        return []
    hint = data.get("protocol")
    protocol = protocol or (hint if isinstance(hint, str) else "") or _api_protocol(data)
    event = str(data.get("type") or data.get("object") or "")
    snapshots = []
    for key in ("usage", "token_usage"):
        usage = _usage_dict(data.get(key))
        if usage is not None:
            snapshots.append(
                {
                    "source": f"{source}.{key}",
                    "usage": deepcopy(usage),
                    "protocol": protocol,
                    "event": event,
                }
            )
    if snapshots:
        return snapshots
    for key in ("response", "message"):
        if data.get(key) is not None:
            snapshots.extend(_api_snapshots(data[key], f"{source}.{key}", protocol=protocol))
    if not snapshots and any(key in data for key in _API_USAGE_KEYS):
        snapshots.append(
            {"source": source, "usage": deepcopy(data), "protocol": protocol, "event": event}
        )
    return snapshots


def _read(
    value: Any, source: str, *, normalized: bool = False, protocol: str = ""
) -> _UsageDetails:
    report = _UsageDetails()
    snapshots = _snapshots(value, source)
    (report.normalized if normalized else report.raw).extend(snapshots)
    messages_fields: dict[str, Any] = {}
    # 同一流中的 usage 为累计快照；每个字段保留最后一个已提供值。
    for snapshot in snapshots:
        current_protocol = snapshot.get("protocol") or protocol
        data = snapshot["usage"]
        if current_protocol in {"messages", "anthropic"}:
            # start 与 delta 各自只提供部分累计字段。
            messages_fields.update({key: value for key, value in data.items() if value is not None})
            data = messages_fields
        parsed = _parse(data, current_protocol)
        for key, count in parsed.items():
            if count is not None:
                report.counts[key] = count
                report.sources[key] = snapshot["source"]
    return report


def _framework_usage_details(response: LLMResult, *, protocol: str = "") -> _UsageDetails:
    """将框架的批次与候选分组转换为同一次调用的 Usage。"""
    output = response.llm_output or {}
    aggregate = _UsageDetails()
    if not protocol:
        protocol = next(
            (
                snapshot["protocol"]
                for group in response.generations or []
                for generation in group
                for snapshot in _snapshots(
                    (
                        getattr(getattr(generation, "message", None), "response_metadata", {}) or {}
                    ).get("sf_raw_usage", []),
                    "",
                )
                if snapshot.get("protocol")
            ),
            "",
        )
    for key in ("token_usage", "usage"):
        if output.get(key) is not None:
            item = _read(output[key], f"llm_output.{key}", protocol=protocol)
            aggregate.fill(item)
            aggregate.raw.extend(item.raw)
    groups = []
    for group_index, generations in enumerate(response.generations or []):
        report = _UsageDetails()
        normalized_reports = []
        for index, generation in enumerate(generations):
            message = getattr(generation, "message", None)
            info = getattr(generation, "generation_info", None) or {}
            metadata = getattr(message, "response_metadata", None) or {}
            prefix = f"generations[{group_index}][{index}]"
            for container, location in (
                (metadata, "message.response_metadata"),
                (info, "generation_info"),
            ):
                for key in ("sf_raw_usage", "token_usage", "usage"):
                    if container.get(key) is not None:
                        item = _read(
                            container[key], f"{prefix}.{location}.{key}", protocol=protocol
                        )
                        report.fill(item)
                        report.raw.extend(item.raw)
            normalized = getattr(message, "usage_metadata", None)
            if normalized is not None:
                item = _read(normalized, f"{prefix}.message.usage_metadata", normalized=True)
                normalized_reports.append(item)
                report.normalized.extend(item.normalized)
        # 先检查全部候选的原始字段，再由标准化数据补齐。
        for item in normalized_reports:
            report.fill(item, fields=("prompt_tokens", "completion_tokens", "cached_prompt_tokens"))
            report.derive(cache=False)
            report.fill(item)
        report.derive()
        groups.append(report)
    combined = _UsageDetails()
    for key in _FIELDS:
        known = [r.counts[key] for r in groups if r.counts[key] is not None]
        if known:
            combined.counts[key] = sum(known)
            combined.sources[key] = ";".join(r.sources[key] for r in groups if key in r.sources)
            if any(r.counts[key] is None or key in r.incomplete_fields for r in groups):
                combined.incomplete_fields.add(key)
    aggregate.fill(combined, fields=("prompt_tokens", "completion_tokens", "cached_prompt_tokens"))
    aggregate.derive()
    aggregate.fill(combined)
    # 推导只使用当前聚合层的原始字段；各输入组在组内独立完成推导。
    aggregate.raw.extend(item for report in groups for item in report.raw)
    aggregate.normalized.extend(item for report in groups for item in report.normalized)
    return aggregate


def _recover_tail(stream: BinaryIO) -> None:
    stream.seek(0, os.SEEK_END)
    end = stream.tell()
    if not end:
        return
    stream.seek(end - 1)
    if stream.read(1) == b"\n":
        return

    cursor = end
    fragments = []
    tail_start = 0
    while cursor:
        start = max(0, cursor - 65536)
        stream.seek(start)
        chunk = stream.read(cursor - start)
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            tail_start = start + newline + 1
            fragments.append(chunk[newline + 1 :])
            break
        fragments.append(chunk)
        cursor = start

    try:
        json.loads(b"".join(reversed(fragments)))
    except (json.JSONDecodeError, UnicodeDecodeError):
        stream.truncate(tail_start)
    else:
        stream.seek(0, os.SEEK_END)
        stream.write(b"\n")


class TokenUsage:
    """按调用 ID 管理 API JSON、SDK 对象和流式 Usage 的累计与落盘。"""

    def __init__(self, usage_path: str | Path | None = None) -> None:
        self.prompt_tokens = self.completion_tokens = self.total_tokens = 0
        self.cached_prompt_tokens = self.llm_calls = self.cache_hit_calls = 0
        self.cache_unreported_calls = self.usage_unreported_calls = 0
        self.usage_recording_errors = 0
        self.by_role: dict[str, dict[str, int]] = {}
        self.usage_path = Path(usage_path) if usage_path is not None else None
        self._lock = threading.RLock()
        self._pending: dict[str, dict[str, Any]] = {}
        self._finished: set[str] = set()

    @staticmethod
    def _parse_result(
        response: Any = None,
        *,
        protocol: str = "",
        observed: Sequence[dict[str, Any]] = (),
        raw_usage: Any = None,
    ) -> _UsageDetails:
        fallback = response if isinstance(response, _UsageDetails) else _UsageDetails()
        snapshots = list(observed)
        if not isinstance(response, _UsageDetails):
            snapshots.extend(_api_snapshots(response, protocol=protocol))
        if raw_usage is not None:
            snapshots.extend(_snapshots(raw_usage, "error.usage"))
        if not snapshots:
            return fallback
        received = _read(snapshots, "usage", protocol=protocol)
        received.fill(fallback, fields=_FIELDS[:2] + (_FIELDS[3],))
        received.derive()
        received.fill(fallback)
        received.raw.extend(fallback.raw)
        received.normalized.extend(fallback.normalized)
        return received

    def observe(self, call_id: str, response: Any, *, protocol: str = "") -> None:
        """保存当前调用已收到的 Usage 快照，供结束或中断时统一累计。"""
        call_id = str(call_id)
        with self._lock:
            if call_id in self._finished:
                return
            pending = self._pending.get(call_id, {})
            observed = pending.get("_usage_snapshots", [])
            snapshots = _api_snapshots(response, f"stream[{len(observed)}]", protocol=protocol)
            if snapshots:
                self._pending.setdefault(call_id, {}).setdefault("_usage_snapshots", []).extend(
                    snapshots
                )

    def begin_call(
        self,
        call_id: str,
        *,
        role: str = "unknown",
        model: str | None = None,
    ) -> None:
        call_id = str(call_id)
        with self._lock:
            if call_id in self._finished:
                return
            pending = self._pending.setdefault(call_id, {})
            if "started_at" in pending:
                return
            pending.update(
                {
                    "started_at": datetime.now(UTC).isoformat(),
                    "role": role,
                    "model": model,
                }
            )

    def finish_call(
        self,
        call_id: str,
        response: Any = None,
        *,
        role: str = "unknown",
        protocol: str = "",
        raw_usage: Any = None,
        error: BaseException | None = None,
    ) -> bool:
        """提交 API 返回值；同 ID 重复终结返回 False。

        protocol 可显式指定接口语义；直接传入 Messages Usage 块时使用 messages。
        流式事件先交给 observe，成功、失败和取消均由此统一结束。
        """
        call_id = str(call_id)
        with self._lock:
            if call_id in self._finished:
                return False
            pending = self._pending.get(call_id, {})
            details = self._parse_result(
                response,
                protocol=protocol,
                raw_usage=raw_usage,
                observed=pending.get("_usage_snapshots", ()),
            )
            started = self._pending.pop(call_id, {})
            started.pop("_usage_snapshots", None)
            role = started.get("role", role)
            status = (
                "cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "error"
                if error is not None
                else "success"
            )
            record = {
                **started,
                "schema_version": 1,
                "call_id": call_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "role": role,
                "status": status,
                "raw_usage_available": any(snapshot["usage"] for snapshot in details.raw),
                "raw_usage": details.raw,
                "normalized_usage": details.normalized,
                "usage": {
                    key: None if key in details.incomplete_fields else value
                    for key, value in details.counts.items()
                },
                **({"known_usage": details.counts} if details.incomplete_fields else {}),
                "usage_sources": details.sources,
                **({"error_type": type(error).__name__} if error is not None else {}),
            }
            self._accumulate(details, role)
            self._finished.add(call_id)
            if self.usage_path is not None:
                try:
                    self._append_record(record)
                except OSError:
                    self.usage_recording_errors += 1
                    self.by_role[role]["usage_recording_errors"] += 1
                    logger.exception("Failed to persist LLM usage to %s", self.usage_path)
            return True

    def _accumulate(self, details: _UsageDetails, role: str) -> None:
        prompt, completion, total, _ = details.values
        cached = details.counts["cached_prompt_tokens"]
        missing_usage = any(
            details.counts[key] is None or key in details.incomplete_fields for key in _FIELDS[:3]
        )
        missing_cache = cached is None or "cached_prompt_tokens" in details.incomplete_fields
        values = dict(
            zip(
                _ROLE_KEYS,
                (
                    prompt,
                    completion,
                    cached or 0,
                    1,
                    int(bool(cached)),
                    int(missing_cache),
                    int(missing_usage),
                    0,
                ),
            )
        )
        for key, value in values.items():
            setattr(self, key, getattr(self, key) + value)
        self.total_tokens += total
        bucket = self.by_role.setdefault(role, dict.fromkeys(_ROLE_KEYS, 0))
        for key, value in values.items():
            bucket[key] += value

    def _append_record(self, record: dict[str, Any]) -> None:
        path = self.usage_path
        if path is None:
            return
        payload = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                _recover_tail(stream)
                stream.seek(0, os.SEEK_END)
                stream.write(payload)
                stream.flush()
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def to_dict(self) -> dict[str, int]:
        # 阶段统计按键求差，只返回整数计数器。
        with self._lock:
            return {key: getattr(self, key) for key in (*_ROLE_KEYS, "total_tokens")}

    @property
    def cache_hit_rate(self) -> float | None:
        with self._lock:
            buckets = [b for role, b in self.by_role.items() if role in MAIN_LOOP_ROLES]
            if buckets:
                if any(b["cache_unreported_calls"] or b["usage_unreported_calls"] for b in buckets):
                    return None
                prompt = sum(b["prompt_tokens"] for b in buckets)
                cached = sum(b["cached_prompt_tokens"] for b in buckets)
            else:
                if self.cache_unreported_calls or self.usage_unreported_calls:
                    return None
                prompt, cached = self.prompt_tokens, self.cached_prompt_tokens
            return cached / prompt if prompt else 0.0

    def __repr__(self) -> str:
        return (
            f"TokenUsage(prompt={self.prompt_tokens}, completion={self.completion_tokens}, "
            f"total={self.total_tokens}, cached={self.cached_prompt_tokens}, "
            f"calls={self.llm_calls})"
        )


_current_usage: ContextVar[TokenUsage | None] = ContextVar("sf_token_usage", default=None)


def start_tracking(usage_path: str | Path | None = None) -> TokenUsage:
    usage = TokenUsage(usage_path)
    _current_usage.set(usage)
    return usage


def get_usage() -> TokenUsage | None:
    return _current_usage.get()


def extract_token_usage(response: Any, *, protocol: str = "") -> tuple[int, int, int, int]:
    if isinstance(response, LLMResult):
        response = _framework_usage_details(response, protocol=protocol)
    return TokenUsage._parse_result(response, protocol=protocol).values


class TokenTrackingCallback(BaseCallbackHandler):
    run_inline = True

    def __init__(self, role: str = "unknown") -> None:
        self.role = role

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs: Any) -> None:
        usage = get_usage()
        if usage is not None:
            params = kwargs.get("invocation_params") or {}
            usage.begin_call(
                str(run_id), role=self.role, model=params.get("model") or params.get("model_name")
            )

    def on_llm_end(self, response: LLMResult, *, run_id=None, **kwargs: Any) -> None:
        self._record(response, run_id=run_id)

    def on_llm_error(self, error: BaseException, *, run_id=None, **kwargs: Any) -> None:
        response = kwargs.get("response")
        self._record(response, run_id=run_id, error=error)

    def _record(
        self,
        response: Any,
        *,
        run_id,
        error: BaseException | None = None,
    ) -> None:
        usage = get_usage()
        if usage is not None:
            if isinstance(response, LLMResult):
                response = _framework_usage_details(response)
            usage.finish_call(
                str(run_id or uuid4()),
                response,
                role=self.role,
                error=error,
                raw_usage=getattr(error, "sf_raw_usage", None),
            )


def usage_snapshot(usage: Any, *, protocol: str, event: str) -> dict[str, Any] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        raw_usage = deepcopy(usage)
    elif hasattr(usage, "model_dump"):
        # 保留厂商扩展字段，且不补入 SDK 默认的空字段。
        raw_usage = usage.model_dump(mode="json", exclude_unset=True)
    else:
        return None
    return {"usage": raw_usage, "protocol": protocol, "event": event}


class _ObservedStream:
    def __init__(self, stream: Any, resource: _ObservedResource):
        self._context_manager = stream
        self._stream = stream
        self._resource = resource

    def __getattr__(self, name: str) -> Any:
        if name == "get_final_completion":
            resource = _ObservedResource(
                self._stream, self._resource._snapshots, self._resource._protocol
            )
            return getattr(resource, name)
        return getattr(self._stream, name)

    def __enter__(self) -> _ObservedStream:
        self._stream = self._context_manager.__enter__()
        return self

    def __exit__(self, *args: Any) -> Any:
        return self._context_manager.__exit__(*args)

    def __iter__(self):
        for event in self._stream:
            self._resource.record(event)
            yield event

    async def __aenter__(self) -> _ObservedStream:
        self._stream = await self._context_manager.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> Any:
        return await self._context_manager.__aexit__(*args)

    async def __aiter__(self):
        async for event in self._stream:
            self._resource.record(event)
            yield event


class _ObservedResource:
    """仅包装当前调用的 SDK 资源，共享客户端本身保持原状。"""

    def __init__(self, resource: Any, snapshots: list[dict[str, Any]], protocol: str):
        self._resource = resource
        self._snapshots = snapshots
        self._protocol = protocol

    def record(self, value: Any) -> None:
        event = getattr(value, "type", None) or (
            "response" if self._protocol == "responses" else "completion"
        )
        response = getattr(value, "response", None)
        if response is not None:
            value = response
        elif getattr(value, "chunk", None) is not None:
            value = value.chunk
        usage = value.get("usage") if isinstance(value, dict) else getattr(value, "usage", None)
        snapshot = usage_snapshot(usage, protocol=self._protocol, event=event)
        if snapshot is not None:
            self._snapshots.append(snapshot)

    def _observe(self, value: Any) -> Any:
        if hasattr(value, "parse"):
            return _ObservedResource(value, self._snapshots, self._protocol)
        if hasattr(value, "__enter__") or hasattr(value, "__aenter__"):
            return _ObservedStream(value, self)
        self.record(value)
        return value

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._resource, name)
        if name in {"responses", "beta", "chat", "completions", "with_raw_response"}:
            protocol = "responses" if name == "responses" else self._protocol
            return _ObservedResource(value, self._snapshots, protocol)
        if name not in {"create", "parse", "stream", "get_final_completion"}:
            return value

        def call(*args: Any, **kwargs: Any) -> Any:
            result = value(*args, **kwargs)
            if isawaitable(result):

                async def await_result() -> Any:
                    return self._observe(await result)

                return await_result()
            return self._observe(result)

        return call


def _attach_snapshots(message: Any, snapshots: list[dict[str, Any]]) -> None:
    if snapshots:
        message.response_metadata.setdefault("sf_raw_usage", []).extend(snapshots)
        snapshots.clear()


def _attach_error_snapshots(error: BaseException, snapshots: list[dict[str, Any]]) -> None:
    if not snapshots:
        return
    try:
        # 保持异常类型及既有错误信息，供失败回调读取已收到的 usage。
        existing = getattr(error, "sf_raw_usage", [])
        error.sf_raw_usage = deepcopy([*snapshots, *existing])  # type: ignore[attr-defined]
    except Exception:
        pass


class UsagePreservingChatOpenAI(ChatOpenAI):
    """保留 Chat Completions 和 Responses 的完整原始 usage。"""

    def _observed_copy(self, snapshots: list[dict[str, Any]]) -> UsagePreservingChatOpenAI:
        # 每次调用独立复制资源引用，允许同一模型并发调用。
        return self.model_copy(
            update={
                name: _ObservedResource(getattr(self, name), snapshots, "chat_completions")
                for name in ("client", "async_client", "root_client", "root_async_client")
                if getattr(self, name, None) is not None
            }
        )

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        snapshots: list[dict[str, Any]] = []
        observed = self._observed_copy(snapshots)
        try:
            result = super(UsagePreservingChatOpenAI, observed)._generate(*args, **kwargs)
        except BaseException as error:
            _attach_error_snapshots(error, snapshots)
            raise
        if result.generations:
            _attach_snapshots(result.generations[0].message, snapshots)
        return result

    async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
        snapshots: list[dict[str, Any]] = []
        observed = self._observed_copy(snapshots)
        try:
            result = await super(UsagePreservingChatOpenAI, observed)._agenerate(*args, **kwargs)
        except BaseException as error:
            _attach_error_snapshots(error, snapshots)
            raise
        if result.generations:
            _attach_snapshots(result.generations[0].message, snapshots)
        return result

    def _stream(self, *args: Any, **kwargs: Any):
        snapshots: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        observed = self._observed_copy(snapshots)
        try:
            for chunk in super(UsagePreservingChatOpenAI, observed)._stream(*args, **kwargs):
                history.extend(snapshots)
                _attach_snapshots(chunk.message, snapshots)
                yield chunk
        except BaseException as error:
            _attach_error_snapshots(error, [*history, *snapshots])
            raise

    async def _astream(self, *args: Any, **kwargs: Any):
        snapshots: list[dict[str, Any]] = []
        history: list[dict[str, Any]] = []
        observed = self._observed_copy(snapshots)
        try:
            async for chunk in super(UsagePreservingChatOpenAI, observed)._astream(*args, **kwargs):
                history.extend(snapshots)
                _attach_snapshots(chunk.message, snapshots)
                yield chunk
        except BaseException as error:
            _attach_error_snapshots(error, [*history, *snapshots])
            raise


class UsagePreservingChatAnthropic(ChatAnthropic):
    http_client: Any = Field(default=None, exclude=True, repr=False)
    http_async_client: Any = Field(default=None, exclude=True, repr=False)

    @cached_property
    def _client(self):
        if self.http_client is None:
            return super()._client
        import anthropic

        return anthropic.Client(**self._client_params, http_client=self.http_client)

    @cached_property
    def _async_client(self):
        if self.http_async_client is None:
            return super()._async_client
        import anthropic

        return anthropic.AsyncClient(**self._client_params, http_client=self.http_async_client)

    def _format_output(self, data: Any, **kwargs: Any) -> Any:
        snapshot = usage_snapshot(data.usage, protocol="anthropic", event="message")
        try:
            result = super()._format_output(data, **kwargs)
        except BaseException as error:
            _attach_error_snapshots(error, [snapshot] if snapshot is not None else [])
            raise
        if snapshot is not None and result.generations:
            result.generations[0].message.response_metadata["sf_raw_usage"] = [snapshot]
        return result

    def _make_message_chunk_from_anthropic_event(self, event: Any, **kwargs: Any) -> Any:
        source = getattr(event, "message", event)
        snapshot = usage_snapshot(
            getattr(source, "usage", None), protocol="anthropic", event=event.type
        )
        try:
            message, block_start_event = super()._make_message_chunk_from_anthropic_event(
                event, **kwargs
            )
        except BaseException as error:
            _attach_error_snapshots(error, [snapshot] if snapshot is not None else [])
            raise
        if snapshot is not None:
            if message is None:
                message = AIMessageChunk(content="")
            message.response_metadata["sf_raw_usage"] = [snapshot]
        return message, block_start_event

    def _stream(self, *args: Any, **kwargs: Any):
        history: list[dict[str, Any]] = []
        try:
            for chunk in super()._stream(*args, **kwargs):
                history.extend(chunk.message.response_metadata.get("sf_raw_usage", []))
                yield chunk
        except BaseException as error:
            _attach_error_snapshots(error, history)
            raise

    async def _astream(self, *args: Any, **kwargs: Any):
        history: list[dict[str, Any]] = []
        try:
            async for chunk in super()._astream(*args, **kwargs):
                history.extend(chunk.message.response_metadata.get("sf_raw_usage", []))
                yield chunk
        except BaseException as error:
            _attach_error_snapshots(error, history)
            raise
