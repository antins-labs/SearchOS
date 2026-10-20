"""后台技能变化归属到原轮次，持久化成功、失败和本次版本。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import searchos.skills as skills
from searchos.skills import PipelineResult, SkillRequest
from searchos.skills.post_run import TraceSkillGeneration, load_generation


def generation(tmp_path):
    workspace = tmp_path / "session"
    workspace.mkdir()
    (workspace / "trajectory.jsonl").write_text('{"type":"task_start","query":"current"}\n')
    return workspace, TraceSkillGeneration(workspace, "current")


@pytest.mark.asyncio
async def test_changes_persist_progress_actions_failures_and_installed_version(
    tmp_path, monkeypatch
):
    workspace, job = generation(tmp_path)
    library = tmp_path / "skills"
    requests = [
        SkillRequest("orchestrator", "new-method", "新方法", reason="任务拆分可复用"),
        SkillRequest(
            "orchestrator", "existing-method", "更新方法", action="update", reason="补充失败重试"
        ),
        SkillRequest("strategy", "failed-method", "失败方法"),
    ]
    stages = []

    async def infer(*args, **kwargs):
        stages.append(load_generation(workspace, job.id))
        return requests

    async def pipeline(request, **kwargs):
        if on_stage := kwargs.get("on_stage"):
            await on_stage("pipeline")
        stages.append(load_generation(workspace, job.id))
        if request.name == "failed-method":
            return PipelineResult(request, "validation_failed", error="答案未获来源支持")
        package = library / request.category.value / request.name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: {request.name}\ndescription: 已验证的能力\nmetadata:\n"
            "  searchos-category: orchestrator\n---\n# 本次版本\n按来源拆分任务。"
        )
        return PipelineResult(request, "installed", path=package)

    monkeypatch.setattr(skills, "infer_requests", infer)
    monkeypatch.setattr(skills, "run_pipeline", pipeline)
    await job.run(library_path=library)
    saved = load_generation(workspace, job.id)
    assert saved["status"] == "completed"
    assert [item["status"] for item in saved["items"]] == [
        "installed",
        "installed",
        "validation_failed",
    ]
    assert [item["action"] for item in saved["items"]] == ["create", "update", "create"]
    assert stages[0]["status"] == "running"
    assert stages[1]["items"][0]["status"] == "running"
    assert stages[2]["items"][0]["status"] == "installed"
    assert saved["items"][0]["description"] == "已验证的能力"
    assert "path" not in saved["items"][0] and "owner_pid" not in saved
    assert "body" not in saved["items"][2]
    (library / "orchestrator/new-method/SKILL.md").write_text("后来修改的版本")
    assert "按来源拆分任务" in load_generation(workspace, job.id)["items"][0]["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_no_changes_and_generation_failure_are_distinct(tmp_path, monkeypatch, failure):
    workspace, job = generation(tmp_path)

    async def infer(*args, **kwargs):
        if failure:
            raise RuntimeError("offline model")
        return []

    monkeypatch.setattr(skills, "infer_requests", infer)
    await job.run(library_path=tmp_path / "skills")
    saved = load_generation(workspace, job.id)
    assert saved["status"] == ("error" if failure else "completed")
    assert saved["items"] == []
    assert bool(saved["error"]) == failure


@pytest.mark.asyncio
async def test_cancellation_retains_installed_changes(tmp_path, monkeypatch):
    workspace, job = generation(tmp_path)

    async def generate(*args, on_progress, **kwargs):
        await on_progress(
            {
                "stage": "planned",
                "requests": [
                    {"name": "first", "action": "create", "category": "orchestrator"},
                    {"name": "second", "action": "update", "category": "strategy"},
                ],
            }
        )
        await on_progress({"stage": "result", "index": 0, "result": {"status": "installed"}})
        await on_progress({"stage": "pipeline", "index": 1})
        raise asyncio.CancelledError

    monkeypatch.setattr(skills, "generate_from_trace", generate)
    with pytest.raises(asyncio.CancelledError):
        await job.run(library_path=tmp_path / "skills")
    saved = load_generation(workspace, job.id)
    assert saved["status"] == "interrupted"
    assert [item["status"] for item in saved["items"]] == ["installed", "interrupted"]


def test_follow_up_input_and_records_do_not_overwrite_previous_run(tmp_path):
    workspace, first = generation(tmp_path)
    trace = workspace / "trajectory.jsonl"
    offset = trace.stat().st_size
    with trace.open("a") as stream:
        stream.write('{"type":"task_start","query":"follow-up"}\n')
    second = TraceSkillGeneration(workspace, "follow-up", trace_offset=offset)
    assert first.id != second.id
    assert "follow-up" not in (first.directory / "trace.jsonl").read_text()
    assert '"current"' not in (second.directory / "trace.jsonl").read_text()
    assert load_generation(workspace, first.id)["query"] == "current"


def test_lost_background_process_is_reported_as_interrupted(tmp_path, monkeypatch):
    from searchos.skills import post_run

    workspace, job = generation(tmp_path)

    def missing(*args):
        raise ProcessLookupError

    monkeypatch.setattr(post_run.os, "kill", missing)
    assert load_generation(workspace, job.id)["status"] == "interrupted"


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_session_result_and_history_share_generation_id(tmp_path, monkeypatch, enabled):
    from searchos.config import models
    from searchos.config.settings import settings
    from searchos.harness import session
    from searchos.harness.middleware import pipelines
    from searchos.skills.catalog.registry import SkillRegistry
    from searchos.socm import SearchState

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes import history, search

    class Model:
        async def ainvoke(self, *args, **kwargs):
            return AIMessage(content='{"is_final_answer": true}')

    monkeypatch.setattr(models, "get_model_for", lambda role: Model())
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_access_skill_generation", enabled)
    monkeypatch.setattr(session, "_premature_end_reason", lambda *_: None)
    gate = asyncio.Event()

    async def infer(*args, **kwargs):
        await gate.wait()
        return []

    monkeypatch.setattr(skills, "infer_requests", infer)

    def build(**kwargs):
        async def stream(payload, **stream_kwargs):
            first = payload["messages"][0]
            yield (
                "values",
                {
                    "messages": [
                        HumanMessage(content=first["content"], id=first.get("id")),
                        AIMessage(content="Research answer"),
                    ]
                },
            )

        return SimpleNamespace(middleware=[], astream=stream)

    monkeypatch.setattr(pipelines, "orchestrator_pipeline", build)
    harness = session.SearchSession(
        workspace_root=str(tmp_path),
        skill_registry=SkillRegistry(),
        max_time_s=30,
        skill_library_path=str(tmp_path / "skills"),
    )
    result = await harness.run(
        "Current question",
        session_id="web-case",
        initial_state=SearchState(intent="Current question"),
        fixed_schema=True,
    )
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(search, "sessions", {"web-case": {"status": "completed", "result": result}})
    try:
        response = await search.get_search_result("web-case")
        restored = await history.load_history("web-case")
        assert response["skill_generation_id"] == result.skill_generation_id
        assert restored["turns"][-1]["skill_generation_id"] == result.skill_generation_id
        if enabled:
            assert result.access_task is not None and not result.access_task.done()
            record = await search.get_skill_generation("web-case", result.skill_generation_id)
            assert record["status"] in {"queued", "running"}
            gate.set()
            await result.access_task
            search.sessions.clear()
            assert (await search.get_skill_generation("web-case", result.skill_generation_id))[
                "status"
            ] == "completed"
        else:
            assert result.skill_generation_id is None and result.access_task is None
            assert not (tmp_path / "web-case/skill_generations").exists()
    finally:
        gate.set()
        if result.access_task:
            await result.access_task


@pytest.mark.asyncio
async def test_api_rejects_wrong_session_and_generation_path(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "web"))
    from api.routes import search
    from fastapi import HTTPException

    workspace, job = generation(tmp_path)
    monkeypatch.setattr(search, "WORKSPACE_ROOT", str(tmp_path))
    for session_id, generation_id in [
        ("session", "../status"),
        ("other", job.id),
        ("session", "a" * 32),
    ]:
        with pytest.raises(HTTPException) as error:
            await search.get_skill_generation(session_id, generation_id)
        assert error.value.status_code == 404
