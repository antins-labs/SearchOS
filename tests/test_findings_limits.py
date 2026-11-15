"""Verify and commit all supported findings without a fixed candidate cap."""

import pytest


@pytest.mark.asyncio
async def test_verified_summary_without_original_is_saved_for_audit_only():
    import json

    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.harness.middleware.extraction.core.findings import extract_and_commit
    from searchos.socm import SearchState
    from searchos.socm.coverage import answer_evidence

    store = InMemoryEvidenceStore(SearchState(intent="Report the total."))
    text = "Regional total: 360."
    responses = iter([[{"finding": text, "source_excerpt": text}], [{"id": "0", "supported": True}]])
    async def invoke(_):
        return json.dumps(next(responses))

    assert await extract_and_commit([{"content": text, "source_url": "agent://search/final_summary"}],
                                    store=store, invoke=invoke) == []
    state = store.load_state()
    node, = state.evidence_graph.nodes
    assert node.status == "candidate" and not answer_evidence(state)
    assert state.evidence_graph.observations[0].id == node.observation_id


@pytest.mark.asyncio
async def test_findings_and_verification_repair_unwrapped_objects():
    import json

    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.harness.middleware.extraction.core.findings import extract_and_commit
    from searchos.socm import SearchState

    fact = "Site A recorded 120 observations."
    row = {"finding": fact, "source_excerpt": fact, "source_urls": []}
    verdict = {"id": "0", "supported": True}
    outputs = iter([row, [row], verdict, [verdict]])
    prompts = []

    async def invoke(prompt):
        prompts.append(prompt)
        return json.dumps(next(outputs))

    store = InMemoryEvidenceStore(SearchState(intent="List observations at Site A."))
    ids = await extract_and_commit(
        [{"content": fact, "source_url": "https://example.org/report"}], store=store, invoke=invoke
    )
    assert len(ids) == 1
    assert len(prompts) == 4
    assert prompts[0] in prompts[1] and prompts[2] in prompts[3]


@pytest.mark.asyncio
async def test_findings_commits_all_task_relevant_facts_beyond_twelve():
    import json

    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.harness.middleware.extraction.core.findings import extract_and_commit
    from searchos.socm import SearchState

    facts = [f"Site {i} recorded {i + 20} observations." for i in range(17)]
    store = InMemoryEvidenceStore(SearchState(intent="List observations for every site."))
    prompts = []

    async def invoke(prompt):
        prompts.append(prompt)
        payload = json.loads(prompt.rsplit("\n", 1)[-1])
        if "candidates" in payload:
            return json.dumps([{"id": row["id"], "supported": True}
                               for row in payload["candidates"]])
        return json.dumps([{"finding": fact, "source_excerpt": fact, "relation": "supports"}
                           for fact in facts])

    committed = await extract_and_commit([{"content": "\n".join(facts), "source_url": "https://example.org/observations"}],
                                         store=store, invoke=invoke)
    assert len(committed) == 17
    assert {node.finding for node in store.load_state().evidence_graph.nodes} == set(facts)
    assert len(prompts) == 2
    assert len(json.loads(prompts[1].rsplit("\n", 1)[-1])["candidates"]) == 17
    assert "最多 12 条" not in prompts[0]
