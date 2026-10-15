"""非法模型输出和待恢复观测只在抽取层重试，不终止检索图。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from searchos.agents.execution import _BeforeModel, _run_resources
from searchos.config.settings import settings
from searchos.harness.middleware.extraction import (
    DeliveryMode, EvidenceObservation, ExtractionConfig, ExtractionCoordinator,
)
from searchos.harness.middleware.extraction.core.judge import RowExtractor
from searchos.harness.middleware.models import TaskContext
from searchos.socm import SearchState
from searchos.socm.frontier import FrontierTask
from searchos.socm.workspace import WorkspaceManager


BAD = '[{"Date":"2026-09-15","Volume":3.67M,"Change":-0.46%}]'
GOOD = '[{"Date":"2026-09-15","Volume":"3.67M","Change":"-0.46%","_source_page":1,"_source_excerpt":"Volume 3.67M; change -0.46%."}]'


class Judge:
    def __init__(self, *outputs):
        self.outputs = outputs
        self.prompts = []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.outputs[min(len(self.prompts) - 1, len(self.outputs) - 1)])


class Log:
    def __init__(self):
        self.events = []

    def _append_raw(self, event):
        self.events.append(event)


@pytest.fixture
def workspace(tmp_path):
    ws = WorkspaceManager(tmp_path, "extraction-recovery")
    ws.create()
    state = SearchState(intent="Collect the reported daily values")
    state.coverage_map.initialize(entities=["2026-09-15"], attributes=["Date", "Volume", "Change"],
                                  primary_key=["Date"], table_id="prices")
    state.frontier.add(FrontierTask(id="same-task", question=state.intent, table_id="prices"))
    ws.save_state(state)
    return ws


def coordinator(ws, judge, agent="agent1", **kwargs):
    return ExtractionCoordinator(judge, workspace=ws, task=TaskContext(agent_id=agent, task_id="same-task"),
                                 config=ExtractionConfig(dual_mode=False, cross_table_backfill=False), **kwargs)


def observation():
    return EvidenceObservation(content="Daily report for 2026-09-15. Volume 3.67M; change -0.46%. Values from the original source.",
                               source_url="https://example.org/daily", target_table="prices", task_id="same-task")


@pytest.mark.asyncio
async def test_invalid_json_is_retried_with_original_context_then_committed(workspace):
    judge = Judge(BAD, GOOD)
    worker = coordinator(workspace, judge)
    receipt = await worker.submit(observation(), delivery=DeliveryMode.SYNC)
    assert receipt.committed_node_ids
    assert len(judge.prompts) == 2
    assert observation().content in judge.prompts[1]
    assert "JSON" in judge.prompts[1][len(judge.prompts[0]):]
    assert all(r["status"] == "done" for r in worker._journal.load())


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", ["[]", "{}", "```json\n[]\n```"])
async def test_valid_empty_result_is_not_retried(workspace, empty):
    judge = Judge(empty)
    receipt = await coordinator(workspace, judge).submit(observation(), delivery=DeliveryMode.SYNC)
    assert all(report.succeeded for report in receipt.extraction_reports)
    assert not receipt.committed_node_ids
    assert len(judge.prompts) == 1


@pytest.mark.asyncio
async def test_failed_recovery_allows_first_model_call_and_preserves_retry(workspace):
    await coordinator(workspace, Judge(GOOD)).submit(observation())
    # Recreate process-local counters while retaining the same journal on disk.
    workspace = WorkspaceManager(workspace.path.parent, workspace.path.name)
    judge, log = Judge(BAD), Log()
    recovered = coordinator(workspace, judge, agent="agent3", trajectory_logger=log)
    calls = []

    async def model(request):
        calls.append(request)

    async with _run_resources((recovered,), timeout=1):
        await _BeforeModel((recovered,)).awrap_model_call("first turn", model)
        await _BeforeModel((recovered,)).awrap_model_call("next turn", model)
    assert calls == ["first turn", "next turn"]
    assert len(judge.prompts) == 3  # no repeated repair on every turn or at finalization
    assert recovered.summary().buffered == 1
    assert workspace.extraction_pending_total == 0  # parked work is not an active flush
    assert any(e["kind"] == "evidence_extraction_deferred" for e in log.events)
    assert recovered._journal.load()[0]["status"] == "failed"
    # A later explicit extraction retry can reuse the same observation, without another search.
    judge.outputs = (GOOD,)
    await recovered.flush()
    assert recovered.summary().buffered == 0
    assert all(r["status"] == "done" for r in recovered._journal.load())


@pytest.mark.asyncio
async def test_slow_recovery_is_bounded_without_blocking_agent(workspace, monkeypatch):
    await coordinator(workspace, Judge(GOOD)).submit(observation())
    monkeypatch.setattr(settings, "extraction_finalize_timeout_s", .02)

    class Slow:
        async def ainvoke(self, prompt):
            await asyncio.Event().wait()

    recovered = coordinator(workspace, Slow(), agent="agent3")
    called = []

    async def model(request):
        called.append(request)

    await asyncio.wait_for(_BeforeModel((recovered,)).awrap_model_call("turn", model), 1)
    assert called == ["turn"]
    assert recovered.summary().buffered == 1


def test_invalid_row_elements_are_not_accepted_as_evidence():
    assert RowExtractor._parse_findings('[1, "text", null]') is None
