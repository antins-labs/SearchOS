"""缺少文章地址的摘要不能生成 URL 证据或填满来源列。"""

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
from searchos.socm import SearchState


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["task_rows", "schema_facts"])
@pytest.mark.parametrize(
    "page_link,value,source,declared,accepted",
    [
        ("publisher.example", "https://publisher.example", "https://roundup.example", [], False),
        (
            "https://publisher.example/story-full",
            "https://publisher.example/story",
            "https://roundup.example",
            [],
            False,
        ),
        (
            "https://publisher.example/story",
            "https://publisher.example",
            "https://roundup.example",
            [],
            False,
        ),
        (
            "https://publisher.example/story",
            "https://publisher.example/story",
            "https://roundup.example",
            [],
            True,
        ),
        (
            "[文章](https://publisher.example/story)",
            "https://publisher.example/story",
            "https://roundup.example",
            [],
            True,
        ),
        (
            "",
            "https://publisher.example/news/20261019",
            "https://publisher.example/news/20261019",
            [],
            True,
        ),
        (
            "",
            "https://publisher.example/story",
            "skill://news/output",
            ["https://publisher.example/story"],
            True,
        ),
        (
            "https://publisher.example/a https://publisher.example/b",
            ["https://publisher.example/a", "https://publisher.example/b"],
            "https://roundup.example",
            [],
            True,
        ),
        (
            "https://publisher.example/a",
            ["https://publisher.example/a", "https://publisher.example/missing"],
            "https://roundup.example",
            [],
            False,
        ),
    ],
)
async def test_url_cells_require_observed_addresses(
    policy, page_link, value, source, declared, accepted
):
    state = SearchState(intent="Collect news with original article links")
    state.coverage_map.initialize(
        entities=["Acme release"],
        attributes=["Title", "Summary", "Original URL"],
        primary_key=["Title"],
        table_id="news",
    )
    quote = "Acme release introduces a new model with improved reasoning capabilities."

    class Judge:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "Title": "Acme release",
                            "Summary": "introduces a new model",
                            "Original URL": value,
                            "_source_page": 1,
                            "_source_excerpt": quote,
                            "_confidence": "high",
                            "_alignment": "full",
                            "_source_urls": declared,
                        }
                    ]
                )
            )

    store = InMemoryEvidenceStore(state)
    coordinator = ExtractionCoordinator(
        Judge(),
        store,
        policy=policy,
        config=ExtractionConfig(dual_mode=False),
    )
    receipt = await coordinator.submit(
        EvidenceObservation(
            content=f"{quote}\n{page_link}",
            source_url=source,
            source_urls=tuple(declared),
            target_table="news",
        ),
        delivery=DeliveryMode.SYNC,
    )

    assert receipt.accepted
    cells = store.state.coverage_map.cells
    assert cells["news/Acme release.Summary"].status.value == "filled"
    url_cell = cells["news/Acme release.Original URL"]
    assert url_cell.status.value == ("filled" if accepted else "missing")
    urls = [store.state.evidence_graph.get_node(fid) for fid in url_cell.supporting_evidence_ids]
    assert len(urls) == int(accepted)
    if accepted:
        # 地址列与引用来源是不同对象，不能把未读取的目标冒充已读取原文。
        assert urls[0].source == source
    else:
        assert not url_cell.supporting_evidence_ids
