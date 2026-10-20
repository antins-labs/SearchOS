"""Verify and commit all supported findings without a fixed candidate cap."""

import pytest


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
