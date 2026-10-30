"""一份开发会话预算、显式验收与失败记录。"""

import json

import pytest
from langchain_core.messages import AIMessage

from searchos.skills.pipeline.access.artifacts import BuildRecord
from searchos.skills.pipeline.access.pipeline import MAX_TURNS, build_skill
from tests.access_pipeline_helpers import (
    Builder, ValidatorModel, call, candidate, examples,
    local_cli as _local_cli,  # noqa: F401
)


def test_default_budget():
    assert MAX_TURNS == 50


@pytest.mark.asyncio
async def test_model_failure_retains_cause_and_attempt_count(tmp_path):
    diagnostics = {}
    assert await build_skill("example.com", [], output_dir=tmp_path / "skill",
        builder_model=Builder(RuntimeError("provider unavailable")),
        record_dir=tmp_path / "record", diagnostics=diagnostics) is None
    assert diagnostics["exit_reason"] == "model_error"
    assert diagnostics["turns_attempted"] == 1 and diagnostics["turns_completed"] == 0
    assert diagnostics["model_error_type"] == "RuntimeError"
    assert json.loads((tmp_path / "record/builder.json").read_text())["exit_reason"] == "model_error"


@pytest.mark.asyncio
async def test_closing_calls_can_repair_and_revalidate_current_candidate(tmp_path, local_cli):
    builder = Builder(candidate(0, {"search": False}, initial=True),
                      candidate(1, {"search": False}), candidate(2, {"search": True}))
    diagnostics = {}
    result = await build_skill("example.com", [], output_dir=tmp_path / "example-com",
        builder_model=builder, validation_model=ValidatorModel(),
        validation_examples=examples("search"), max_turns=1, validation_max_turns=1,
        record_dir=tmp_path / "record", diagnostics=diagnostics)
    assert result is not None and builder.calls == 3
    assert diagnostics["turns_completed"] == 3
    assert diagnostics["validation_rounds"] == 3
    assert diagnostics["capability_results"]["search"]["status"] == "available"
    assert "REVISION = 2" in (result / "scripts/access.py").read_text()
    events = [json.loads(line) for line in (tmp_path / "record/events.jsonl").read_text().splitlines()]
    assert [item["closing"] for item in events if item["event"] == "model_started"] == [False, True, True]
    assert not any("finalization_tool_blocked" in item.get("content", "")
                   for item in events if item["event"] == "tool_result")
    assert not any(item["event"] == "repair_started" for item in events)


@pytest.mark.asyncio
async def test_closing_call_can_submit_a_repaired_candidate(tmp_path, local_cli):
    builder = Builder(candidate(0, {"search": True}, initial=True, submit=False),
                      AIMessage(content="交接当前候选", tool_calls=[
                          call("send_message", "submit", role="validator", content={"request": "validate"})]))
    diagnostics = {}
    await build_skill("example.com", [], output_dir=tmp_path / "example-com",
        builder_model=builder, validation_model=ValidatorModel(),
        validation_examples=examples("search"), max_turns=1, validation_max_turns=1,
        record_dir=tmp_path / "record", diagnostics=diagnostics)
    assert builder.calls == 2 and diagnostics["valid"]
    assert any("收尾" in str(message.content) for message in builder.messages[-1])


@pytest.mark.asyncio
async def test_final_response_prompts_explicit_validation_before_fallback(tmp_path, local_cli):
    builder = Builder(candidate(0, {"search": True}, initial=True, submit=False),
                      AIMessage(content="实现已完成。"),
                      AIMessage(content="交接验收", tool_calls=[
                          call("send_message", "submit", role="validator", content={"request": "validate"})]))
    diagnostics = {}
    await build_skill("example.com", [], output_dir=tmp_path / "example-com",
        builder_model=builder, validation_model=ValidatorModel(),
        validation_examples=examples("search"), max_turns=2, validation_max_turns=1,
        record_dir=tmp_path / "record", diagnostics=diagnostics)
    assert diagnostics["valid"] and diagnostics["validation_rounds"] == 1
    assert builder.calls == 3
    assert any("当前版本尚未完成修复或独立验收" in str(message.content) for message in builder.messages[-1])


@pytest.mark.asyncio
async def test_post_submission_edit_gets_final_validation_handoff(tmp_path, local_cli):
    first = candidate(0, {"search": True}, initial=True)
    first.tool_calls.append(call("edit_file", "late-edit", path="scripts/access.py",
                                 old_text="REVISION = 0", new_text="REVISION = 1"))
    builder = Builder(first, AIMessage(content="保留尚未复验的文件。"))
    diagnostics = {}
    await build_skill("example.com", [], output_dir=tmp_path / "example-com",
        builder_model=builder, validation_model=ValidatorModel(),
        validation_examples=examples("search"), max_turns=1, validation_max_turns=1,
        record_dir=tmp_path / "record", diagnostics=diagnostics)
    assert diagnostics["validation_rounds"] == 2
    assert diagnostics["valid"] and diagnostics["final_validation_handoff"]
    assert diagnostics["capability_results"]["search"]["status"] == "available"


def test_record_redacts_env_credentials_and_private_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "private-test-key-123")
    record = BuildRecord(tmp_path / "record")
    record.event("tool_result", content="token private-test-key-123", args={"authorization": "secret"})
    saved = (record.root / "events.jsonl").read_text()
    assert "private-test-key-123" not in saved and '"secret"' not in saved
    assert "[REDACTED]" in saved


@pytest.mark.asyncio
async def test_pipeline_failure_points_to_persistent_builder_record(tmp_path):
    from searchos.skills import SkillRequest, run_pipeline

    result = await run_pipeline(
        SkillRequest("access", "example-com", "读取记录", host="example.com",
                     probe_urls=("https://example.com/",)),
        library_path=tmp_path / "library", trial_root=tmp_path / "trials",
        model=Builder(RuntimeError("provider unavailable")))
    assert result.status == "build_failed"
    saved = json.loads(result.trial_path.read_text())
    assert saved["diagnostics"]["exit_reason"] == "model_error"
    assert (result.trial_path.parent / "builder.json").is_file()
