"""Shared LLM JSON invocation, text extraction, and token estimation for local indexing."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from searchos.local import messages
from searchos.local.errors import RecapValidationError
from searchos.utils.json_extract import extract_json_object

logger = logging.getLogger(__name__)


def message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                value = block.get("text") or block.get("content")
                if value:
                    parts.append(str(value))
        return "\n".join(parts)
    return str(content or "")


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(char.isascii() for char in text)
    return (ascii_chars + 2) // 3 + (len(text) - ascii_chars) * 2


def supports_kwarg(fn: Any, name: str) -> bool:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
    )


def _supports_json_mode(model: Any) -> bool:
    if not hasattr(model, "bind"):
        return False
    cls_name = type(model).__name__
    if "Anthropic" in cls_name:
        return False
    return hasattr(model, "openai_api_base") or hasattr(model, "model_kwargs")


async def _ainvoke_with_optional_json_mode(model: Any, chat_messages: list[Any]) -> Any:
    if _supports_json_mode(model):
        try:
            bound = model.bind(response_format={"type": "json_object"})
            return await bound.ainvoke(chat_messages)
        except Exception as exc:  # noqa: BLE001
            # Some OpenAI-compatible gateways reject response_format; fall back cleanly.
            msg = str(exc).lower()
            if any(token in msg for token in ("response_format", "json_object", "unsupported", "400")):
                logger.debug("model rejected response_format=json_object, falling back: %s", exc)
            else:
                raise
    return await model.ainvoke(chat_messages)


async def invoke_json(
    model: Any,
    *,
    system_prompt: str,
    prompt: str,
    schema: type[BaseModel],
    error_message: str = messages.MODEL_JSON_INVALID,
    repair_prompt_builder: Callable[[str, str], str] | None = None,
) -> dict[str, Any]:
    """Invoke a chat model expecting JSON, validate with Pydantic, and retry once with error details."""

    base_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt),
    ]
    response = await _ainvoke_with_optional_json_mode(model, base_messages)
    raw_text = message_text(response)
    payload = extract_json_object(raw_text)
    validation_error: str | None = None
    if payload is None:
        validation_error = messages.MODEL_JSON_INVALID
    else:
        try:
            schema.model_validate(payload)
            return payload
        except ValidationError as exc:
            validation_error = str(exc)

    logger.warning("local model JSON/schema validation failed, retrying once: %s", validation_error)
    repair_text = (
        repair_prompt_builder(raw_text, validation_error)
        if repair_prompt_builder is not None
        else (
            f"你上一次的输出未通过校验（错误：{validation_error}）。"
            "请只修正格式或字段问题，重新返回一个完整的合法 JSON 对象，不要附加任何说明。\n\n"
            f"上一次输出：\n{raw_text[:2000]}"
        )
    )
    retry_messages = [
        *base_messages,
        AIMessage(content=raw_text or "(empty)"),
        HumanMessage(content=repair_text),
    ]
    retry_response = await _ainvoke_with_optional_json_mode(model, retry_messages)
    retry_raw = message_text(retry_response)
    retry_payload = extract_json_object(retry_raw)
    if retry_payload is None:
        raise RecapValidationError(error_message)
    try:
        schema.model_validate(retry_payload)
    except ValidationError as exc:
        raise RecapValidationError(error_message) from exc
    return retry_payload


__all__ = ["estimate_tokens", "invoke_json", "message_text", "supports_kwarg"]
