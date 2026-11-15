"""验证回调在调用边界保存 usage 及其缺失状态。"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import BaseModel, ConfigDict

from searchos.harness.telemetry.usage import TokenTrackingCallback, TokenUsage, start_tracking


def response(raw=None, normalized=None):
    return LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="正文不进入usage日志",
                        usage_metadata=normalized,
                        response_metadata={"sf_raw_usage": raw} if raw is not None else {},
                    )
                )
            ]
        ]
    )


def read_records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_raw_usage_saved_at_callback_boundary_without_request_content(tmp_path):
    path = tmp_path / "output/llm_usage.jsonl"
    usage = start_tracking(path)
    callback = TokenTrackingCallback("orchestrator")
    call_id = uuid4()
    callback.on_chat_model_start(
        {},
        [[AIMessage(content="请求正文")]],
        run_id=call_id,
        invocation_params={"model": "test-model", "api_key": "secret"},
    )
    raw = [
        {
            "protocol": "chat_completions",
            "event": "completion",
            "usage": {
                "prompt_tokens": 16025,
                "completion_tokens": 56,
                "total_tokens": 16081,
                "prompt_cache_hit_tokens": 14336,
                "vendor_extra": {"retained": True},
            },
        }
    ]
    callback.on_llm_end(
        response(
            raw,
            {
                "input_tokens": 16025,
                "output_tokens": 56,
                "total_tokens": 16081,
            },
        ),
        run_id=call_id,
    )
    (record,) = read_records(path)
    assert record["call_id"] == str(call_id)
    assert record["model"] == "test-model"
    assert record["started_at"] <= record["timestamp"]
    assert record["raw_usage_available"] is True
    assert record["raw_usage"][0]["usage"] == raw[0]["usage"]
    assert record["usage"]["cached_prompt_tokens"] == 14336
    assert usage.cache_hit_rate == pytest.approx(14336 / 16025)
    assert all(value not in path.read_text() for value in ("secret", "请求正文", "正文不进入"))


def test_normalized_cache_fallback_preserves_missing_raw_status(tmp_path):
    path = tmp_path / "llm_usage.jsonl"
    usage = start_tracking(path)
    TokenTrackingCallback("orchestrator").on_llm_end(
        response(
            normalized={
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "input_token_details": {"cache_read": 0},
            }
        )
    )
    (record,) = read_records(path)
    assert record["raw_usage_available"] is False
    assert record["usage"]["cached_prompt_tokens"] == 0
    assert "usage_metadata" in record["usage_sources"]["cached_prompt_tokens"]
    assert usage.cache_hit_rate == 0


def test_missing_usage_records_call_and_unknown_cache(tmp_path):
    path = tmp_path / "llm_usage.jsonl"
    usage = start_tracking(path)
    TokenTrackingCallback("orchestrator").on_llm_end(response())
    (record,) = read_records(path)
    assert record["usage"] == dict.fromkeys(
        ("prompt_tokens", "completion_tokens", "total_tokens", "cached_prompt_tokens")
    )
    assert record["raw_usage_available"] is False
    assert usage.llm_calls == usage.cache_unreported_calls == usage.usage_unreported_calls == 1
    assert usage.cache_hit_rate is None


@pytest.mark.parametrize("error", [RuntimeError("failed"), asyncio.CancelledError()])
def test_error_callback_retains_already_received_raw_usage(tmp_path, error):
    path = tmp_path / "llm_usage.jsonl"
    usage = start_tracking(path)
    error.sf_raw_usage = [
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_cache_hit_tokens": 40,
            },
            "protocol": "chat_completions",
            "event": "completion",
        }
    ]
    TokenTrackingCallback("sub_agent").on_llm_error(error, run_id=uuid4())
    (record,) = read_records(path)
    expected_status = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
    assert record["status"] == expected_status
    assert record["error_type"] == type(error).__name__
    assert record["usage"]["cached_prompt_tokens"] == usage.cached_prompt_tokens == 40


def test_cache_miss_derivation_is_saved_with_its_source(tmp_path):
    path = tmp_path / "llm_usage.jsonl"
    start_tracking(path)
    TokenTrackingCallback().on_llm_end(
        response(
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_cache_miss_tokens": 60,
            }
        )
    )
    (record,) = read_records(path)
    assert record["usage"]["cached_prompt_tokens"] == 40
    assert record["usage_sources"]["cached_prompt_tokens"].startswith("derived:")


def test_recording_error_is_exposed_in_run_summary(tmp_path, monkeypatch, caplog):
    usage = start_tracking(tmp_path / "usage.jsonl")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(TokenUsage, "_append_record", fail)
    TokenTrackingCallback("orchestrator").on_llm_end(
        response(
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_cache_hit_tokens": 40,
            }
        )
    )
    assert usage.to_dict()["usage_recording_errors"] == 1
    assert usage.by_role["orchestrator"]["usage_recording_errors"] == 1
    assert "Failed to persist LLM usage" in caplog.text


@pytest.mark.parametrize(
    "outcomes",
    [
        ("success", "success"),
        ("error", "error"),
        ("success", "error"),
        ("error", "success"),
        ("cancelled", "cancelled"),
    ],
)
@pytest.mark.parametrize("persist", [False, True])
def test_terminal_callbacks_count_one_call(tmp_path, outcomes, persist):
    path = tmp_path / "usage.jsonl"
    usage = start_tracking(path if persist else None)
    callback = TokenTrackingCallback("orchestrator")
    call_id = uuid4()
    raw = {"prompt_tokens": 100, "completion_tokens": 20, "prompt_cache_hit_tokens": 40}
    callback.on_chat_model_start({}, [], run_id=call_id, invocation_params={"model": "test-model"})
    for outcome in outcomes:
        if outcome == "success":
            callback.on_llm_end(response(raw), run_id=call_id)
        else:
            error = asyncio.CancelledError() if outcome == "cancelled" else RuntimeError("failed")
            error.sf_raw_usage = raw
            callback.on_llm_error(error, run_id=call_id)
    assert usage.llm_calls == 1
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (100, 20, 120)
    assert usage.by_role["orchestrator"]["llm_calls"] == 1
    if persist:
        (record,) = read_records(path)
        assert record["status"] == outcomes[0]
        assert record["model"] == "test-model"


@pytest.mark.parametrize("shared_call", [False, True])
def test_core_serializes_concurrent_call_completion(tmp_path, shared_call):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    barrier = Barrier(8)

    def finish(index):
        barrier.wait(timeout=5)
        return usage.finish_call(
            "shared" if shared_call else str(index),
            {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_cache_hit_tokens": 40,
                }
            },
            role="sub_agent",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        completed = list(pool.map(finish, range(8)))
    expected = 1 if shared_call else 8
    assert sum(completed) == usage.llm_calls == len(read_records(path)) == expected
    assert usage.prompt_tokens == expected * 100


def test_cancelled_error_subclass_keeps_cancelled_status(tmp_path):
    class CancelledRequest(asyncio.CancelledError):
        pass

    path = tmp_path / "usage.jsonl"
    start_tracking(path)
    TokenTrackingCallback().on_llm_error(CancelledRequest(), run_id=uuid4())
    (record,) = read_records(path)
    assert record["status"] == "cancelled"
    assert record["error_type"] == "CancelledRequest"


def test_error_raw_usage_can_fill_missing_counts_from_partial_response(tmp_path):
    path = tmp_path / "usage.jsonl"
    usage = start_tracking(path)
    error = RuntimeError("stream interrupted")
    error.sf_raw_usage = {"prompt_tokens": 110, "prompt_cache_hit_tokens": 40}
    TokenTrackingCallback().on_llm_error(
        error,
        run_id=uuid4(),
        response=response(
            normalized={
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
                "input_token_details": {"cache_read": 0},
            }
        ),
    )
    (record,) = read_records(path)
    assert record["usage"] == {
        "prompt_tokens": 110,
        "completion_tokens": 20,
        "total_tokens": 130,
        "cached_prompt_tokens": 40,
    }
    assert usage.total_tokens == 130
    assert record["raw_usage"][0]["usage"] == error.sf_raw_usage
    assert record["normalized_usage"]


def test_log_failure_does_not_recount_or_block_later_calls(tmp_path, monkeypatch):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    result = {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    original_append = TokenUsage._append_record

    def fail(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(TokenUsage, "_append_record", fail)
    assert usage.finish_call("failed-log", result, role="orchestrator")
    usage.begin_call("failed-log", role="orchestrator")
    assert not usage.finish_call("failed-log", result, role="orchestrator")
    assert usage.llm_calls == usage.usage_recording_errors == 1
    monkeypatch.setattr(TokenUsage, "_append_record", original_append)
    assert usage.finish_call("next-call", result, role="orchestrator")
    assert usage.llm_calls == 2
    (record,) = read_records(path)
    assert record["call_id"] == "next-call"


class APIResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


@pytest.mark.parametrize(
    "container", [dict, APIResponse.model_validate, lambda value: SimpleNamespace(**value)]
)
@pytest.mark.parametrize(
    "payload,protocol,expected",
    [
        (
            {
                "object": "chat.completion",
                "choices": [{"message": {"content": "private reply"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "prompt_tokens_details": {"cached_tokens": 40},
                    "completion_tokens_details": {"reasoning_tokens": 10},
                },
            },
            "openai_compatible",
            (100, 20, 120, 40),
        ),
        (
            {
                "model": "another-vendor",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_cache_hit_tokens": 40,
                    "vendor_extension": {"preserved": True},
                },
            },
            "openai_compatible",
            (100, 20, 120, 40),
        ),
        (
            {
                "type": "response.completed",
                "response": {
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "input_tokens_details": {"cached_tokens": 40},
                    }
                },
            },
            "",
            (100, 20, 120, 40),
        ),
        (
            {
                "type": "message",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 30,
                },
            },
            "",
            (170, 20, 190, 40),
        ),
        (
            {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 40},
            "openai_compatible",
            (100, 20, 120, 40),
        ),
    ],
)
def test_core_accepts_api_json_and_sdk_objects(tmp_path, container, payload, protocol, expected):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    assert usage.finish_call("api-call", container(payload), protocol=protocol)
    assert (
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
        usage.cached_prompt_tokens,
    ) == expected
    (record,) = read_records(path)
    assert tuple(record["usage"].values()) == expected
    assert "private reply" not in path.read_text()
    if payload.get("model") == "another-vendor":
        assert record["raw_usage"][0]["usage"]["vendor_extension"] == {"preserved": True}


@pytest.mark.parametrize("error", [None, RuntimeError("interrupted"), asyncio.CancelledError()])
def test_stream_usage_survives_finish_and_interruption(tmp_path, error):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    usage.begin_call("stream", role="orchestrator", model="compatible-model")
    usage.observe("stream", {"choices": [{"delta": {"content": "private stream text"}}]})
    event = {
        "object": "chat.completion.chunk",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 40},
        },
    }
    usage.observe("stream", event, protocol="openai_compatible")
    usage.observe("stream", event, protocol="openai_compatible")
    event["usage"]["prompt_tokens_details"]["cached_tokens"] = 0
    assert usage.finish_call("stream", error=error)
    usage.observe("stream", {"usage": {"prompt_tokens": 999}})
    assert not usage.finish_call("stream", {"usage": {"prompt_tokens": 999}})
    (record,) = read_records(path)
    assert usage.llm_calls == 1
    assert record["usage"] == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "cached_prompt_tokens": 40,
    }
    assert record["role"] == "orchestrator"
    assert record["status"] == (
        "cancelled"
        if isinstance(error, asyncio.CancelledError)
        else "error"
        if error
        else "success"
    )
    assert "private stream text" not in path.read_text()


def test_core_combines_messages_start_and_delta_usage(tmp_path):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    usage.observe(
        "messages",
        {
            "type": "message_start",
            "message": {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 30,
                }
            },
        },
    )
    usage.observe("messages", {"type": "message_delta", "usage": {"output_tokens": 20}})
    usage.finish_call("messages")
    (record,) = read_records(path)
    assert record["usage"] == {
        "prompt_tokens": 170,
        "completion_tokens": 20,
        "total_tokens": 190,
        "cached_prompt_tokens": 40,
    }


def test_core_accepts_openai_sdk_usage_object(tmp_path):
    from openai.types import CompletionUsage

    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    result = CompletionUsage(
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        prompt_tokens_details={"cached_tokens": 40},
    )
    usage.finish_call("sdk-usage", result)
    assert usage.total_tokens == 120
    assert usage.cached_prompt_tokens == 40


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"choices": [{"message": {"content": "private reply"}}], "usage": None},
    ],
)
def test_unreported_api_usage_stays_unknown(tmp_path, payload):
    path = tmp_path / "usage.jsonl"
    usage = TokenUsage(path)
    usage.finish_call("missing", payload)
    (record,) = read_records(path)
    assert record["usage"] == dict.fromkeys(record["usage"])
    assert not record["raw_usage_available"]
    assert usage.usage_unreported_calls == 1
    assert "private reply" not in path.read_text()


def test_interface_protocol_controls_counts_independently_of_provider_label():
    from searchos.harness.telemetry.usage import extract_token_usage

    result = LLMResult(
        generations=[],
        llm_output={
            "model_provider": "anthropic",
            "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 40},
        },
    )
    assert extract_token_usage(result, protocol="openai_compatible") == (100, 20, 120, 40)
    assert extract_token_usage(result, protocol="anthropic") == (140, 20, 160, 40)
    assert extract_token_usage(result, protocol="messages") == (140, 20, 160, 40)
    assert extract_token_usage(
        {
            "protocol": {"vendor_extension": True},
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
    ) == (100, 20, 120, 0)
