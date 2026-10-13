"""模型调用兼容：仅在明确不支持图片时转换输入并重试。"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any


async def call_model(request: Any, handler: Callable, *, image_fallback: bool = True) -> Any:
    if not image_fallback:
        return await handler(request)
    try:
        return await handler(request)
    except Exception as exc:
        from searchos.tools.simple_browser.image_reading import (
            is_explicitly_unsupported,
            mark_native_unsupported,
            replace_native_image_tool_results,
        )

        has_image = any(
            isinstance(message.content, list)
            and any(
                isinstance(block, dict) and block.get("type") in {"image", "image_url"}
                for block in message.content
            )
            for message in request.messages
        )
        if not has_image or not is_explicitly_unsupported(exc):
            raise
        model = getattr(request, "model", None)
        if model is not None:
            mark_native_unsupported(model, str(exc))
        messages = await replace_native_image_tool_results(list(request.messages))
        return await handler(replace(request, messages=messages))
