"""通过真实 SDK 的离线 HTTP 响应验证原始 usage 保留。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

DEEPSEEK_USAGE = {
    "prompt_tokens": 16000,
    "completion_tokens": 120,
    "total_tokens": 16120,
    "prompt_cache_hit_tokens": 14336,
    "prompt_cache_miss_tokens": 1664,
    "provider_extension": {"request_class": "cached"},
}
OPENAI_USAGE = {
    "prompt_tokens": 16000,
    "completion_tokens": 120,
    "total_tokens": 16120,
    "prompt_tokens_details": {"cached_tokens": 14336},
}


class UsageCallback(BaseCallbackHandler):
    def __init__(self):
        self.results = []
        self.errors = []

    def on_llm_end(self, response, **kwargs):
        self.results.append(response)

    def on_llm_error(self, error, **kwargs):
        self.errors.append(error)


def _chat_stream(*usages):
    chunks = [
        {
            "id": "chat-test",
            "object": "chat.completion.chunk",
            "model": "test-model",
            "created": 1,
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}}],
        },
        *[
            {
                "id": "chat-test",
                "object": "chat.completion.chunk",
                "model": "test-model",
                "created": 1,
                "choices": [],
                "usage": usage,
            }
            for usage in usages
        ],
    ]
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def _model(model_class, payload, *, streaming=True, **kwargs):
    def handle(request):
        assert request.url.host == "offline.invalid"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream" if streaming else "application/json"},
            content=payload if streaming else json.dumps(payload),
        )

    transport = httpx.MockTransport(handle)
    return model_class(
        model="test-model",
        api_key="offline-key",
        base_url="https://offline.invalid/v1",
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
        max_retries=0,
        stream_usage=True,
        **kwargs,
    )


def test_unadapted_sdk_stream_drops_deepseek_cache_fields():
    model = _model(ChatOpenAI, _chat_stream(DEEPSEEK_USAGE))
    chunks = list(model.stream("test"))
    message = sum(chunks[1:], chunks[0])
    assert message.usage_metadata["input_tokens"] == 16000
    assert message.usage_metadata.get("input_token_details", {}).get("cache_read", 0) == 0
    assert "sf_raw_usage" not in message.response_metadata


@pytest.mark.asyncio
@pytest.mark.parametrize("usage", [DEEPSEEK_USAGE, OPENAI_USAGE])
async def test_async_chat_stream_preserves_provider_usage_for_callbacks(usage):
    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    callback = UsageCallback()
    model = _model(
        UsagePreservingChatOpenAI,
        _chat_stream(usage),
        callbacks=[callback],
    )
    chunks = [chunk async for chunk in model.astream("test")]
    message = sum(chunks[1:], chunks[0])
    snapshot = message.response_metadata["sf_raw_usage"][0]
    assert snapshot["protocol"] == "chat_completions"
    assert snapshot["usage"] == usage
    callback_message = callback.results[0].generations[0][0].message
    assert callback_message.response_metadata["sf_raw_usage"] == [snapshot]
    from searchos.harness.telemetry.usage import extract_token_usage

    assert extract_token_usage(callback.results[0]) == (16000, 120, 16120, 14336)


def test_chat_usage_snapshots_do_not_sum_repeated_cumulative_counts():
    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    model = _model(UsagePreservingChatOpenAI, _chat_stream(DEEPSEEK_USAGE, DEEPSEEK_USAGE))
    chunks = list(model.stream("test"))
    message = sum(chunks[1:], chunks[0])
    snapshots = message.response_metadata["sf_raw_usage"]
    assert len(snapshots) == 2
    assert [item["usage"]["prompt_cache_hit_tokens"] for item in snapshots] == [14336, 14336]


def _chat_response(usage):
    return {
        "id": "chat-test",
        "object": "chat.completion",
        "model": "test-model",
        "created": 1,
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "ok"},
        }],
        "usage": usage,
    }


@pytest.mark.parametrize("async_call", [False, True])
def test_nonstream_chat_response_keeps_exact_raw_usage(async_call):
    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    callback = UsageCallback()
    model = _model(
        UsagePreservingChatOpenAI,
        _chat_response(DEEPSEEK_USAGE),
        streaming=False,
        callbacks=[callback],
    )
    message = asyncio.run(model.ainvoke("test")) if async_call else model.invoke("test")
    assert message.response_metadata["sf_raw_usage"][0]["usage"] == DEEPSEEK_USAGE
    assert callback.results[0].generations[0][0].message.response_metadata["sf_raw_usage"]


@pytest.mark.parametrize("async_call", [False, True])
def test_failed_chat_stream_exposes_received_usage_to_error_callback(async_call):
    import openai

    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    payload = _chat_stream(DEEPSEEK_USAGE).replace("data: [DONE]\n\n", "")
    payload += 'data: {"error": {"type": "server_error", "message": "offline failure"}}\n\n'
    callback = UsageCallback()
    model = _model(UsagePreservingChatOpenAI, payload, callbacks=[callback])
    with pytest.raises(openai.APIError) as failure:
        if async_call:
            async def collect():
                return [chunk async for chunk in model.astream("test")]

            asyncio.run(collect())
        else:
            list(model.stream("test"))
    assert failure.value.sf_raw_usage[0]["usage"] == DEEPSEEK_USAGE
    assert len(failure.value.sf_raw_usage) == 1
    assert callback.errors[0] is failure.value


def _responses_response():
    return {
        "id": "resp-test",
        "object": "response",
        "created_at": 1,
        "status": "completed",
        "model": "test-model",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "metadata": {},
        "parallel_tool_calls": True,
        "temperature": 1,
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1,
        "service_tier": "default",
        "text": {"format": {"type": "text"}},
        "output": [{
            "type": "message",
            "id": "msg-test",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "ok", "annotations": []}],
        }],
        "usage": {
            "input_tokens": 16000,
            "output_tokens": 120,
            "total_tokens": 16120,
            "input_tokens_details": {"cached_tokens": 14336},
            "output_tokens_details": {"reasoning_tokens": 0},
            "provider_extension": {"request_class": "cached"},
        },
    }


def _responses_stream():
    response = _responses_response()
    events = [
        {"type": "response.created", "sequence_number": 0, "response": {
            **response, "status": "in_progress", "usage": None, "output": [],
        }},
        {
            "type": "response.output_text.delta", "sequence_number": 1,
            "item_id": "msg-test", "output_index": 0, "content_index": 0, "delta": "ok",
        },
        {"type": "response.completed", "sequence_number": 2, "response": response},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


@pytest.mark.parametrize("async_call", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
def test_responses_api_preserves_raw_usage(async_call, streaming):
    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    callback = UsageCallback()
    model = _model(
        UsagePreservingChatOpenAI,
        _responses_stream() if streaming else _responses_response(),
        streaming=streaming,
        use_responses_api=True,
        callbacks=[callback],
    )
    if streaming:
        async def collect():
            return [chunk async for chunk in model.astream("test")]

        chunks = asyncio.run(collect()) if async_call else list(model.stream("test"))
        message = sum(chunks[1:], chunks[0])
    else:
        message = asyncio.run(model.ainvoke("test")) if async_call else model.invoke("test")
    snapshots = message.response_metadata["sf_raw_usage"]
    assert len(snapshots) == 1
    assert snapshots[0]["protocol"] == "responses"
    assert snapshots[0]["usage"] == _responses_response()["usage"]
    assert callback.results[0].generations[0][0].message.response_metadata["sf_raw_usage"]
    from searchos.harness.telemetry.usage import extract_token_usage

    assert extract_token_usage(callback.results[0]) == (16000, 120, 16120, 14336)


@pytest.mark.asyncio
async def test_parallel_calls_keep_usage_snapshots_separate():
    from searchos.harness.telemetry.usage import UsagePreservingChatOpenAI

    async def handle(request):
        body = json.loads(request.content)
        cached = int(body["messages"][0]["content"])
        await asyncio.sleep(0)
        usage = {**DEEPSEEK_USAGE, "prompt_cache_hit_tokens": cached}
        return httpx.Response(200, json=_chat_response(usage))

    model = UsagePreservingChatOpenAI(
        model="test-model", api_key="offline-key", base_url="https://offline.invalid/v1",
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    results = await asyncio.gather(model.ainvoke("1024"), model.ainvoke("2048"))
    assert [m.response_metadata["sf_raw_usage"][0]["usage"]["prompt_cache_hit_tokens"]
            for m in results] == [1024, 2048]


def _anthropic_response():
    return {
        "id": "msg-test", "type": "message", "role": "assistant", "model": "test-model",
        "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {
            "input_tokens": 120, "output_tokens": 20,
            "cache_creation_input_tokens": 544, "cache_read_input_tokens": 14336,
            "provider_extension": {"request_class": "cached"},
        },
    }


def _anthropic_stream():
    response = _anthropic_response()
    events = [
        {"type": "message_start", "message": {
            **response, "content": [], "stop_reason": None,
            "usage": {**response["usage"], "output_tokens": 0},
        }},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "text_delta", "text": "ok"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 20}},
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _anthropic_model(callback, payload, *, streaming=True):
    import anthropic

    from searchos.harness.telemetry.usage import UsagePreservingChatAnthropic

    def handle(request):
        assert request.url.host == "offline.invalid"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream" if streaming else "application/json"},
            content=payload if streaming else json.dumps(payload),
        )

    model = UsagePreservingChatAnthropic(model="test-model", api_key="offline-key",
                                        callbacks=[callback], max_retries=0)
    model._client = anthropic.Anthropic(
        api_key="offline-key", base_url="https://offline.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    model._async_client = anthropic.AsyncAnthropic(
        api_key="offline-key", base_url="https://offline.invalid",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    return model


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("async_call", [False, True])
def test_anthropic_usage_keeps_start_and_delta_without_defaults(streaming, async_call):
    callback = UsageCallback()
    model = _anthropic_model(
        callback,
        _anthropic_stream() if streaming else _anthropic_response(),
        streaming=streaming,
    )
    if streaming:
        async def collect():
            return [chunk async for chunk in model.astream("test")]

        chunks = asyncio.run(collect()) if async_call else list(model.stream("test"))
        message = sum(chunks[1:], chunks[0])
        snapshots = message.response_metadata["sf_raw_usage"]
        assert [s["event"] for s in snapshots] == ["message_start", "message_delta"]
        assert snapshots[0]["usage"] == {**_anthropic_response()["usage"], "output_tokens": 0}
        assert snapshots[1]["usage"] == {"output_tokens": 20}
    else:
        message = asyncio.run(model.ainvoke("test")) if async_call else model.invoke("test")
        expected = _anthropic_response()["usage"]
        assert message.response_metadata["sf_raw_usage"][0]["usage"] == expected
    assert callback.results[0].generations[0][0].message.response_metadata["sf_raw_usage"]
    from searchos.harness.telemetry.usage import extract_token_usage

    assert extract_token_usage(callback.results[0]) == (15000, 20, 15020, 14336)


@pytest.mark.parametrize("async_call", [False, True])
def test_failed_anthropic_stream_keeps_usage_snapshots(async_call):
    import anthropic

    payload = _anthropic_stream().split("event: message_stop", 1)[0]
    payload += ('event: error\ndata: {"type": "error", "error": '
                '{"type": "overloaded_error", "message": "offline failure"}}\n\n')
    callback = UsageCallback()
    model = _anthropic_model(callback, payload)
    with pytest.raises(anthropic.APIError) as failure:
        if async_call:
            async def collect():
                return [chunk async for chunk in model.astream("test")]

            asyncio.run(collect())
        else:
            list(model.stream("test"))
    snapshots = failure.value.sf_raw_usage
    assert [snapshot["event"] for snapshot in snapshots] == ["message_start", "message_delta"]
    assert snapshots[0]["usage"]["cache_read_input_tokens"] == 14336
    assert callback.errors[0] is failure.value


@pytest.mark.parametrize("provider", ["openai_compatible", "openai", "anthropic"])
def test_config_constructs_usage_preserving_models(monkeypatch, provider):
    from searchos.config import models
    from searchos.config.profiles import ModelProfile
    from searchos.harness.telemetry.usage import (
        UsagePreservingChatAnthropic,
        UsagePreservingChatOpenAI,
    )

    profile = ModelProfile(
        model="offline-model", provider=provider, api_key_fallback="offline-key",
        api_base="https://offline.invalid/v1", api_key_env="OFFLINE_USAGE_TEST_KEY",
    )
    monkeypatch.setattr(models, "resolve_profile", lambda role: profile)
    monkeypatch.setattr(models, "_rate_limit_kwargs", lambda profile: {})
    result = models.get_model_for("orchestrator")
    expected = (
        UsagePreservingChatAnthropic if provider == "anthropic" else UsagePreservingChatOpenAI
    )
    assert isinstance(result, expected)
