"""Hybrid 由已声明 schema 决定来源抽取形态。"""

import json
from types import SimpleNamespace

import pytest

from searchos.harness.middleware.extraction import (
    DeliveryMode,
    EvidenceObservation,
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.harness.middleware.extraction.core.commit import ingest_facts
from searchos.harness.middleware.extraction.core.preparation import OriginalWindowPreparer
from searchos.harness.middleware.extraction.core.routing import SchemaRouting, TaskRouting
from searchos.socm import FrontierTask, SearchState


@pytest.mark.asyncio
@pytest.mark.parametrize("source_mode", ["web", "hybrid"])
@pytest.mark.parametrize("target", ["", "fees"])
@pytest.mark.parametrize("delayed_schema", [False, True])
async def test_schema_routes_findings_to_tables_at_flush(target, delayed_schema, source_mode):
    state = SearchState(research_mode="findings", source_scope={"mode": source_mode})
    state.frontier.add(
        FrontierTask(
            id="read", question="Check Alpha requirements", result_mode="findings", table_id=target
        )
    )
    store = InMemoryEvidenceStore(state)

    def add_schema():
        store.state.coverage_map.add_table(
            "credits", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
        )
        store.state.coverage_map.add_table(
            "fees", ["Name", "Fee"], primary_key=["Name"], entities=["Alpha"]
        )

    if not delayed_schema:
        add_schema()

    class Judge:
        async def ainvoke(self, prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Name": "Alpha",
                            "Credits": "120",
                            "Fee": "50",
                            "_alignment": "full",
                            "_confidence": "high",
                            "_source_excerpt": (
                                "Alpha requires 120 credits and charges a fee of 50."
                            ),
                        }
                    ]
                )
            )

    coordinator = ExtractionCoordinator(
        Judge(),
        store,
        preparer=OriginalWindowPreparer(
            ExtractionConfig(dual_mode=False, cross_table_backfill=False)
        ),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        batch_n=10,
        config=ExtractionConfig(dual_mode=False, cross_table_backfill=False),
    )
    receipt = await coordinator.submit(
        EvidenceObservation(
            task_id="read",
            result_mode="findings",
            source_url="https://example.org/alpha",
            content="Official requirements: Alpha requires 120 credits and charges a fee of 50.",
        ),
        delivery=DeliveryMode.BUFFERED if delayed_schema else DeliveryMode.SYNC,
    )
    assert receipt.accepted
    if delayed_schema:
        add_schema()
        await coordinator.finalize()
    assert store.state.coverage_map.cells["fees/Alpha.Fee"].value == "50"
    assert store.state.coverage_map.cells["credits/Alpha.Credits"].value == (
        "120" if not target else ""
    )
    ids = {b.evidence_id for b in store.state.evidence_graph.task_bindings if b.task_id == "read"}
    assert ids and set(coordinator.committed_node_ids) <= ids


@pytest.mark.asyncio
async def test_saved_source_extraction_also_follows_new_schema():
    from searchos.harness.middleware.extraction.core.replay import extract_saved_observation
    from searchos.socm.evidence import SourceObservation

    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid"})
    state.frontier.add(
        FrontierTask(
            id="read", question="Check credits", result_mode="findings", agent_type="search_agent"
        )
    )
    source = SourceObservation.capture(
        "https://example.org/alpha",
        "Official programme requirements: Alpha requires 120 credits. Applies to 2026 entrants.",
    )
    state.evidence_graph.observations.append(source)
    state.coverage_map.add_table(
        "credits", ["Name", "Credits"], primary_key=["Name"], entities=["Alpha"]
    )
    store = InMemoryEvidenceStore(state)

    async def invoke(prompt):
        return json.dumps(
            [
                {
                    "Name": "Alpha",
                    "Credits": "120",
                    "_alignment": "full",
                    "_confidence": "high",
                    "_source_excerpt": "Alpha requires 120 credits.",
                }
            ]
        )

    result = await extract_saved_observation(
        store, invoke, task_id="read", observation_id=source.id
    )
    assert result["evidence_ids"]
    assert store.state.coverage_map.cells["credits/Alpha.Credits"].value == "120"
    assert store.state.evidence_graph.observations[0] == source
    assert {b.task_id for b in store.state.evidence_graph.task_bindings} == {"read"}


@pytest.mark.asyncio
@pytest.mark.parametrize("source_mode", ["web", "hybrid"])
@pytest.mark.parametrize("routing, expected", [(TaskRouting, "findings"), (SchemaRouting, "table")])
async def test_selected_routing_controls_acceptance_mode(source_mode, routing, expected):
    state = SearchState(research_mode="findings", source_scope={"mode": source_mode})
    state.coverage_map.add_table("facts", ["Name", "Value"], primary_key=["Name"])
    coordinator = ExtractionCoordinator(
        None,
        InMemoryEvidenceStore(state),
        commit_rows=ingest_facts,
        preparer=OriginalWindowPreparer(ExtractionConfig()),
        routing=routing(),
    )
    receipt = await coordinator.submit(
        EvidenceObservation(
            content="A sufficiently detailed original source for routing mode verification.",
            source_url="https://example.org/source",
        )
    )
    assert receipt.accepted
    assert coordinator._pending_buffer[0]["result_mode"] == expected


def test_schema_routing_reports_missing_target_without_silently_reassigning():
    state = SearchState()
    state.coverage_map.add_table("remaining", ["Name", "Value"], primary_key=["Name"])
    item = {"target_table": "removed", "task_id": "task", "content": "source"}
    routed, rejected = SchemaRouting().expand(state, [item])
    assert routed == []
    assert rejected == [(item, "removed")]
