"""工具保留可操作来源与原文，宿主审计字段不进入模型上下文。"""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from searchos.socm import EvidenceNode, SearchState
from searchos.socm.evidence import SourceObservation
from searchos.tools.skills import execution
from searchos.tools.socm_read import evidence


def sample_state():
    source = "local://document/s1?v=" + "a" * 24
    text = "The project started in 2024."
    metadata = {
        "file_name": "report.pdf", "ref_id": source,
        "representation_id": "pdf:native_text", "representation_selector": "primary",
        "source_locator": [{"type": "pdf", "page_start": 3, "page_end": 3}],
        "text_range": {"start": 0, "end": len(text)}, "coverage": "full",
        "extraction_method": ["native_text"], "warnings": ["Check the footnote."],
        "excerpt_hash": "sha256:" + "b" * 64, "source_revision": "a" * 64,
        "verification": {"artifact_integrity": True, "content_reviewed": False},
        "internal_debug": {"sha256": "c" * 64},
    }
    observation = SourceObservation.capture(source, text, metadata)
    node = EvidenceNode(
        id="fact", finding=text, source=source, source_excerpt=text,
        local_source_metadata=metadata, observation_id=observation.id,
        page_id="a" * 12, text_hash="sha1:" + "d" * 40,
        span=(0, len(text)), created_at=1234.0,
    )
    state = SearchState(intent="When did the project start?")
    state.evidence_graph.add_node(node)
    state.evidence_graph.observations.append(observation)
    return state


def sample_execution():
    return {
        "execution_id": "exec-sample", "status": "completed", "exit_code": 0,
        "page_url": "skill://sample/exec-sample/result",
        "index_page_url": "skill://sample/exec-sample/index",
        "pages": [{"url": "skill://sample/exec-sample/result", "title": "Result",
                   "kind": "skill_result"}], "pages_total": 1,
        "started": True, "legacy": False, "backend": "sandbox-exec",
        "capabilities": {"disk_quota": "polled", "process_cleanup": "process-group"},
        "stdout": "Saved output", "stderr": "", "truncated": False, "timed_out": False,
        "artifacts": [{"path": "result.json", "sha256": "a" * 64}],
        "package_hash": "b" * 64, "internal_debug": {"meta": "host only"},
    }


@pytest.mark.asyncio
async def test_evidence_tools_preserve_reading_handles_without_audit_hashes(monkeypatch):
    state = sample_state()
    before = state.model_dump()
    monkeypatch.setattr(evidence, "_ws", lambda: SimpleNamespace(load_state=lambda: state))
    response = json.loads(await evidence.read_evidence.ainvoke({"evidence_ids": "fact"}))
    node = response["nodes"][0]
    assert not {"text_hash", "created_at", "page_id"} & node.keys()
    assert node["observation_id"] == state.evidence_graph.observations[0].id
    assert node["citation"] == "evidence:fact"
    assert node["source_excerpt"] == state.evidence_graph.nodes[0].source_excerpt
    metadata = node["local_source_metadata"]
    hidden = {"excerpt_hash", "source_revision", "verification", "internal_debug"}
    assert not hidden & metadata.keys()
    for key in ("file_name", "representation_id", "representation_selector",
                "source_locator", "coverage", "warnings", "extraction_method"):
        assert metadata[key] == state.evidence_graph.nodes[0].local_source_metadata[key]
    traced = json.loads(await evidence.resolve_cell_provenance.ainvoke({"evidence_id": "fact"}))
    record = traced["records"][0]
    assert not {"text_hash", "observation_text_hash", "page_id"} & record.keys()
    assert record["observation_id"] == node["observation_id"]
    assert record["span"] == {"start_char": 0, "end_char": len(node["source_excerpt"])}
    assert record["snippet"] == node["source_excerpt"]
    assert state.model_dump() == before


@pytest.mark.asyncio
async def test_load_skill_only_exposes_instructions_and_invocation(monkeypatch):
    package = {
        "name": "sample", "body": "Use run.py to retrieve the source.",
        "category": "access", "description": "Find a source", "compatibility": "Python 3",
        "resources": ["run.py"], "resources_truncated": False,
        "execution": "cli", "invocation": "exec(skill=name, argv=['python', 'run.py'])",
        "package_hash": "a" * 64, "directory": "/internal/packages/" + "a" * 64,
        "work_directory": "/internal/work/task", "availability": "enabled",
        "internal_debug": "host only",
    }
    before = deepcopy(package)
    monkeypatch.setattr(execution, "load_package", lambda name: package)
    result = json.loads(await execution.load_skill.ainvoke({"skill_name": "sample"}))
    assert not {"package_hash", "directory", "work_directory", "availability",
                "internal_debug"} & result.keys()
    assert result["body"] == package["body"]
    assert result["resources"] == package["resources"]
    assert result["invocation"] == package["invocation"]
    assert package == before


def test_execution_receipt_keeps_controls_in_artifact_and_preserves_diagnostics():
    record = sample_execution()
    before = deepcopy(record)
    content, artifact = execution._execution_response(record)
    visible = json.loads(content)
    assert not {"started", "legacy", "backend", "capabilities", "package_hash",
                "internal_debug", "artifacts", "stdout", "stderr", "timed_out",
                "truncated"} & visible.keys()
    assert visible["read_result"]["arguments"]["id_or_url"] == record["page_url"]
    assert artifact["execution"] == before and record == before
    failure = {**record, "status": "failed", "exit_code": 1, "stderr": "Retry with a query.",
               "auth_required": True, "truncated": True, "replayed": True}
    failed, _ = execution._execution_response(failure)
    failed = json.loads(failed)
    assert failed["stderr"] == failure["stderr"]
    assert failed["auth_required"] and failed["truncated"] and failed["replayed"]


def test_original_source_json_keeps_user_relevant_meta_and_sha_fields():
    from searchos.tools.simple_browser.result_pages import format_skill_result

    source = {"meta": {"release": "2026"}, "files": [{"name": "model.bin", "sha256": "a" * 64}]}
    assert json.loads(format_skill_result(source)) == source


@pytest.mark.asyncio
async def test_local_find_keeps_navigation_once_and_original_metadata_in_artifact(monkeypatch):
    from searchos.harness.middleware.extraction.local_middleware import LocalEvidenceMiddleware
    from searchos.local.reader import tools

    ref = "local://document/s1?v=" + "a" * 24
    text = "The project started in 2024.\n" * 12
    source = SimpleNamespace(
        ref_id=ref, title="Report", display_path="report.pdf", text=text,
        source_locators=[], representation_ids=("pdf:native_text",),
        representation_selector="primary", coverage="full", warnings=(),
        source_revision="a" * 64, extraction_methods=("native_text",),
    )
    monkeypatch.setattr(tools, "_state", lambda: None)
    monkeypatch.setattr(tools, "_load_source", lambda *args, **kwargs: source)
    found = await tools.local_find.ainvoke({
        "type": "tool_call", "name": "local_find", "id": "find",
        "args": {"ref_id": ref, "pattern": "project"},
    })
    assert found.content.count("Metadata:") == 1
    assert found.content.count("local_open(") == 1
    assert found.content.count("# Match") == 12
    assert ref in found.content and "pdf:native_text" in found.content
    assert "source_revision" not in found.content and "excerpt_hash" not in found.content
    assert found.artifact["navigation_only"] is True
    assert found.artifact["local_source_metadata"]["source_revision"] == "a" * 64
    opened = await tools.local_open.ainvoke({
        "type": "tool_call", "name": "local_open", "id": "open",
        "args": {"ref_id": ref, "loc": 4, "max_chars": 20, "representation_id": "primary"},
    })
    assert opened.content.split("\n\n", 1)[1] == text[4:24]
    assert opened.artifact["local_source_metadata"]["text_range"] == {"start": 4, "end": 24}
    fallback = LocalEvidenceMiddleware._extract_local_source_metadata(opened.content, ref)
    assert fallback["ref_id"] == ref
    assert fallback["text_range"] == {"start": 4, "end": 24}
    assert fallback["representation_id"] == "pdf:native_text"


def test_task_report_keeps_facts_once_and_preserves_unverified_worker_brief():
    from searchos.socm.coverage import answer_evidence
    from searchos.tools.tasks.reports import _ground_search_report

    state = sample_state()
    report = {"last_message": "A lead that still needs investigation.",
              "evidence_bindings": [{"evidence_id": "fact"}]}
    _ground_search_report(report, answer_evidence(state))
    assert report["grounded_findings"][0]["finding"] == state.evidence_graph.nodes[0].finding
    assert report["grounded_findings"][0]["citation"] == "evidence:fact"
    assert state.evidence_graph.nodes[0].finding not in report["last_message"]
    assert report["agent_report"] == {
        "verified": False, "text": "A lead that still needs investigation.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["web", "hybrid"])
async def test_check_agents_batch_keeps_task_evidence_and_returns_each_report_once(
    tmp_path, monkeypatch, mode,
):
    from searchos.agents.runtime import _ctx, set_orchestrator_context
    from searchos.socm import FrontierTask, SearchReport
    from searchos.socm.evidence import EvidenceStatus, bind_task_evidence
    from searchos.socm.storage.workspace import WorkspaceManager
    from searchos.tools.tasks import reports

    state = SearchState(research_mode="findings", source_scope={"mode": mode, "documents": []})
    for task_id in ("first", "second"):
        state.frontier.add(FrontierTask(id=task_id, question=task_id))
    facts = [f"fact-{index}" for index in range(30)]
    for fact_id in [*facts, "other", "rejected"]:
        state.evidence_graph.add_node(EvidenceNode(
            id=fact_id, finding=fact_id, source=f"https://example.org/{fact_id}",
        ))
    bind_task_evidence(state, "first", [*facts, "rejected"])
    bind_task_evidence(state, "second", [facts[0], "other"])
    state.evidence_graph.get_node("rejected").status = EvidenceStatus.REJECTED
    workspace = WorkspaceManager(tmp_path, "batch-reports")
    workspace.create()
    workspace.save_state(state)
    set_orchestrator_context(workspace=workspace, model=object())
    scheduler = SimpleNamespace(tick=AsyncMock(return_value={}))
    monkeypatch.setattr(reports, "_scheduler", lambda: scheduler)
    for task_id in ("first", "second"):
        _ctx.completed[task_id] = SearchReport(
            agent_id=task_id, task_ids=[task_id], status="completed", last_message=task_id,
        )
        _ctx.task_pool[task_id] = asyncio.create_task(asyncio.sleep(0))
    await asyncio.gather(*_ctx.task_pool.values())
    running = asyncio.create_task(asyncio.Event().wait())
    _ctx.task_pool["running"] = running
    try:
        payload = json.loads(await reports.check_agents.ainvoke({}))
        first, second = payload["reports"]
        assert first["task_ids"] == ["first"] and second["task_ids"] == ["second"]
        assert [item["id"] for item in first["grounded_findings"]] == facts[:24]
        assert first["grounded_findings_total"] == 30
        assert {binding["evidence_id"] for binding in first["evidence_bindings"]} == set(facts)
        assert [item["id"] for item in second["grounded_findings"]] == [facts[0], "other"]
        assert first["agent_report"] == {"verified": False, "text": "first"}
        assert _ctx.completed["first"].last_message == "first"
        assert payload["remaining"] == 1 and payload["running_ids"] == ["running"]
        assert not running.done()

        again = json.loads(await reports.check_agents.ainvoke({"timeout": 0.001}))
        assert again["reports"] == [] and again["remaining"] == 1
        assert not running.done()
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
