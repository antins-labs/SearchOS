"""评测默认先探索；验证配置隔离、真实会话接线与例外路径。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from searchos.config.run_config import (
    EffectiveRunConfig,
    activate_run_config,
    current_run_config,
)
from searchos.config.settings import settings


@pytest.mark.parametrize("enabled", [False, True])
def test_eval_initial_explore_is_task_local_and_respects_ablation(monkeypatch, enabled):
    monkeypatch.setattr(settings, "enable_explore", enabled)
    product = EffectiveRunConfig.from_settings()
    evaluation = EffectiveRunConfig.from_settings(for_eval=True)
    assert product.explore_on_start is False
    assert evaluation.explore_on_start is enabled
    assert evaluation.snapshot()["explore_on_start"] is enabled
    with activate_run_config(product):
        with activate_run_config(evaluation):
            assert current_run_config().explore_on_start is enabled
        assert current_run_config().explore_on_start is False


@pytest.mark.parametrize(
    "for_eval, mode, run_kwargs, enabled, web_available, expected",
    [
        (False, "web", {}, True, True, False),
        (True, "web", {}, True, True, True),
        (True, "hybrid", {}, True, True, True),
        (True, "web", {"fixed_schema": True}, True, True, True),
        (True, "web", {"follow_up": True}, True, True, False),
        (True, "web", {"context_preamble": "Prior evidence"}, True, True, False),
        (True, "web", {"targeted_repair_cells": []}, True, True, False),
        (True, "web", {}, False, True, False),
        (True, "hybrid", {}, True, False, False),
    ],
)
def test_session_applies_initial_explore_policy(
    monkeypatch, tmp_path, for_eval, mode, run_kwargs, enabled, web_available, expected,
):
    from searchos.config import models
    from searchos.harness.session import SearchSession
    from searchos.harness.telemetry.conversation import ConversationLogger
    from searchos.skills.catalog.registry import SkillRegistry
    from searchos.socm import SearchState

    monkeypatch.setattr(models, "get_model_for", lambda role: object())
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_explore", True)
    # 捕获配置之后禁用 Explore，也必须服从当前 Agent Catalog。
    config = EffectiveRunConfig.from_settings(for_eval=for_eval)
    monkeypatch.setattr(settings, "enable_explore", enabled)
    session = SearchSession(
        skill_registry=SkillRegistry(),
        workspace_root=str(tmp_path),
        run_config=config,
    )
    scope = {"mode": mode, "documents": []}
    if not web_available:
        scope["unavailable_sources"] = {"web": "Web is unavailable"}
    state = SearchState(intent="lookup", source_scope=scope)
    if run_kwargs.get("fixed_schema"):
        state.coverage_map.add_table("items", ["Name", "Value"], primary_key=["Name"])

    class PromptCaptured(Exception):
        pass

    captured = {}

    def capture(self, **kwargs):
        captured.update(kwargs)
        raise PromptCaptured

    monkeypatch.setattr(ConversationLogger, "register_sub_agent", capture)
    with pytest.raises(PromptCaptured):
        asyncio.run(session.run("lookup", initial_state=state, **run_kwargs))
    prompt = captured["system_prompt"]
    assert ("Begin this new research task" in prompt) is expected
    if expected:
        assert "The first tool call MUST be" in prompt
        assert "do not repeat initial exploration" in prompt
        assert "no minimum number of tool waves" in prompt.lower()
        assert "during Search" in prompt
        assert "Explore is optional" not in prompt
    if run_kwargs.get("fixed_schema"):
        assert "Explore must not redesign the schema" in prompt
        assert "Explore only when a concrete uncertainty blocks retrieval" not in prompt
    if not enabled or not web_available:
        assert "Explore is disabled" in prompt


@pytest.mark.asyncio
async def test_benchmark_passes_initial_explore_config_to_session_and_metadata(monkeypatch, tmp_path):
    from eval import runner
    from searchos.harness import session as session_module

    monkeypatch.setattr(settings, "enable_explore", True)
    captured = []

    def session_factory(**kwargs):
        captured.append(kwargs["run_config"])
        return object()

    async def run_one(sample, **kwargs):
        kwargs["harness_factory"](str(tmp_path / sample.id))
        assert kwargs["experiment_config"]["run_config"]["explore_on_start"] is True
        return {}

    monkeypatch.setattr(session_module, "SearchSession", session_factory)
    monkeypatch.setattr(session_module, "wait_for_all_evolutions", AsyncMock())
    monkeypatch.setattr(session_module, "close_browser_service", AsyncMock())
    monkeypatch.setattr(runner, "_run_one", run_one)
    monkeypatch.setattr(runner, "aggregate_widesearch", lambda rows: {})
    monkeypatch.setattr(runner, "_reproducibility_snapshot", lambda: {})
    await runner.run_benchmark(
        benchmark="widesearch", samples=[SimpleNamespace(id="probe")],
        grade_fn=lambda *_: {}, output_dir=tmp_path,
    )
    assert len(captured) == 1
    assert captured[0].source == "eval" and captured[0].explore_on_start is True
    assert EffectiveRunConfig.from_settings().explore_on_start is False
