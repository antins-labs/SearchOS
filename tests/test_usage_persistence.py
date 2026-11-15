"""验证会话接线、逐调用落盘和中断后的记录保留。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from searchos.config.settings import settings
from searchos.harness.session import SearchSession
from searchos.harness.telemetry import usage as token_tracker
from searchos.skills.catalog.registry import SkillRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_session_starts_tracking_in_resolved_workspace(tmp_path, monkeypatch, legacy):
    from searchos.config import models

    root = tmp_path / "runs"
    old_id = "0b7daafb688c"
    requested_id = old_id if legacy else "new-session"
    actual_id = "20261023_120000_" + old_id if legacy else requested_id
    expected_workspace = root / actual_id
    if legacy:
        expected_workspace.mkdir(parents=True)
    monkeypatch.setattr(settings, "output_dir", "usage-output")
    monkeypatch.setattr(models, "get_model_for", lambda role: object())
    harness = SearchSession(workspace_root=str(root), skill_registry=SkillRegistry())
    captured = []

    class TrackingConfigured(Exception):
        pass

    def capture_tracking(*, usage_path):
        assert expected_workspace.is_dir()
        captured.append(usage_path)
        raise TrackingConfigured

    monkeypatch.setattr(token_tracker, "start_tracking", capture_tracking)
    with pytest.raises(TrackingConfigured):
        await harness.run("测试工作区", session_id=requested_id)
    assert captured == [expected_workspace / "usage-output" / "llm_usage.jsonl"]
    if legacy:
        assert not (root / old_id).exists()


def _report_usage(prompt_tokens: int) -> None:
    token_tracker.TokenTrackingCallback(role="sub_agent").on_llm_end(LLMResult(
        generations=[[ChatGeneration(message=AIMessage(content="离线回答"))]],
        llm_output={"token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": 7,
            "total_tokens": prompt_tokens + 7,
            "prompt_cache_hit_tokens": prompt_tokens // 2,
            "provider_extension": {"request": prompt_tokens},
        }},
    ))


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["error", "cancel"])
async def test_local_calls_are_saved_before_completion_and_survive_stop(
    tmp_path, monkeypatch, stop,
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.assistant import runtime
    from api.routes import local_search

    root = tmp_path / "runs"
    monkeypatch.setattr(settings, "output_dir", "usage-output")
    monkeypatch.setattr(local_search, "WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(local_search, "sessions", {})
    monkeypatch.setattr(runtime, "get_runtime", lambda: SimpleNamespace(
        before_replace=AsyncMock(),
    ))
    started = {query: asyncio.Event() for query in ("first", "second")}
    release = asyncio.Event()
    prompts = {"first": 120, "second": 246}

    async def answer(_library, _documents, query, **_kwargs):
        _report_usage(prompts[query])
        started[query].set()
        await release.wait()
        raise RuntimeError("offline interruption")

    monkeypatch.setattr(local_search, "_service", lambda: SimpleNamespace(answer=answer))
    parent_usage = token_tracker.get_usage()
    tasks = []
    paths = {}
    for query in prompts:
        await local_search.launch_local_search(
            session_id=query, query=query, library_id="test-library",
            document_ids=["test-document"], history=None,
        )
        tasks.append(local_search.sessions[query]["task"])
        paths[query] = root / query / "usage-output" / "llm_usage.jsonl"
    try:
        await asyncio.sleep(0)
        for task in tasks:
            if task.done():
                task.result()
        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in started.values())), timeout=5,
        )
        # 模型回调完成后立即可读；后台回答仍在等待。
        for query, expected_prompt in prompts.items():
            assert local_search.sessions[query]["status"] == "running"
            records = _records(paths[query])
            assert len(records) == 1
            assert records[0]["role"] == "sub_agent"
            assert records[0]["usage"]["prompt_tokens"] == expected_prompt
            assert records[0]["raw_usage_available"] is True
            raw_usage = json.dumps(records[0]["raw_usage"])
            assert "provider_extension" in raw_usage
            assert str(expected_prompt) in raw_usage
        assert token_tracker.get_usage() is parent_usage
        if stop == "cancel":
            for task in tasks:
                task.cancel()
        else:
            release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        if stop == "cancel":
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
        for query in prompts:
            assert local_search.sessions[query]["status"] == "error"
            assert len(_records(paths[query])) == 1
        release.set()
        await local_search.launch_local_search(
            session_id="first", query="first", library_id="test-library",
            document_ids=["test-document"], history=None,
        )
        await local_search.sessions["first"]["task"]
        assert len(_records(paths["first"])) == 2
        assert len(_records(paths["second"])) == 1
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
