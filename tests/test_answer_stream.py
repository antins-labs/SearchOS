from __future__ import annotations

from types import SimpleNamespace

import pytest

from searchos.harness.answer_stream import AnswerStreamEmitter, message_chunk_text


def test_answer_stream_coalesces_chunks_and_preserves_whitespace():
    events: list[dict] = []
    stream = AnswerStreamEmitter(events.append, stream_prefix="answer", flush_chars=20)

    stream.push("第一段")
    stream.push(" 回答")
    stream.finish()

    assert events == [
        {
            "type": "answer_stream_start",
            "stream_id": "answer-1",
            "phase": "final_answer",
        },
        {
            "type": "answer_stream_delta",
            "stream_id": "answer-1",
            "phase": "final_answer",
            "delta": "第一段",
        },
        {
            "type": "answer_stream_delta",
            "stream_id": "answer-1",
            "phase": "final_answer",
            "delta": " 回答",
        },
    ]


def test_answer_stream_resets_between_model_invocations():
    events: list[dict] = []
    stream = AnswerStreamEmitter(events.append, stream_prefix="answer")

    stream.push("中间说明")
    stream.finish()
    stream.push("最终答案")
    stream.finish()

    assert [event["stream_id"] for event in events] == [
        "answer-1", "answer-1", "answer-2", "answer-2",
    ]


def test_message_chunk_text_supports_string_and_content_blocks():
    assert message_chunk_text(SimpleNamespace(content="a b")) == "a b"
    assert message_chunk_text(SimpleNamespace(content=[
        {"type": "text", "text": "甲"},
        " ",
        {"type": "text", "text": "乙"},
    ])) == "甲 乙"


@pytest.mark.asyncio
async def test_writer_finalize_does_not_publish_model_chunks(monkeypatch):
    from searchos.agents import runtime
    from searchos.harness.session import _run_writer_finalize

    class StreamingGraph:
        async def astream(self, _input, *, config, stream_mode):
            assert config["configurable"]["thread_id"] == "writer-thread"
            assert stream_mode == ["values"]
            yield "values", {"messages": []}
            yield "values", {
                "messages": [SimpleNamespace(type="ai", content="最终答案")],
            }

    monkeypatch.setattr(runtime, "_ctx", SimpleNamespace(agent_graphs={
        "writer_1": {
            "agent_type": "writer_agent",
            "started_at": 1.0,
            "graph": StreamingGraph(),
            "thread_id": "writer-thread",
        },
    }))
    result = await _run_writer_finalize(
        query="测试",
        coverage_table="",
        sources_list="",
        language="中文",
        coverage_score=1.0,
    )

    assert result == ("最终答案", "writer_1")
