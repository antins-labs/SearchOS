"""抽取构造依赖不受隐藏运行模式或全局设置影响。"""

import pytest

from searchos.config.settings import settings
from searchos.harness.middleware.extraction import (
    ExtractionConfig,
    ExtractionCoordinator,
    InMemoryEvidenceStore,
)
from searchos.harness.middleware.extraction.core.preparation import (
    ObservationPreparer,
    OriginalWindowPreparer,
)
from searchos.socm import SearchState


@pytest.mark.parametrize("source_mode", ["web", "hybrid"])
def test_window_processing_depends_on_selected_preparer(source_mode):
    windows = [
        {
            "source_url": "https://example.org/source",
            "content": f"L0: window {index}",
            "source_kind": "page",
            "source_mode": source_mode,
            "content_hash": str(index),
        }
        for index in range(2)
    ]
    config = ExtractionConfig()
    merged = ObservationPreparer(config).prepare_pages(windows)
    original = OriginalWindowPreparer(config).prepare_pages(windows)
    assert len(merged) == 1
    assert "window 0" in merged[0]["content"] and "window 1" in merged[0]["content"]
    assert len(original) == 2
    assert [item["observation_text"] for item in original] == [w["content"] for w in windows]


def test_default_coordinator_does_not_load_global_extraction_flags(monkeypatch):
    monkeypatch.setattr(settings, "extraction_dual_mode", False)
    coordinator = ExtractionCoordinator(None, InMemoryEvidenceStore(SearchState()))
    assert coordinator._config.dual_mode is True
    configured = ExtractionCoordinator(
        None,
        InMemoryEvidenceStore(SearchState()),
        config=ExtractionConfig.from_settings(),
    )
    assert configured._config.dual_mode is False


def test_chunk_overlap_is_an_explicit_parameter(monkeypatch):
    monkeypatch.setattr(settings, "extraction_chunk_overlap_chars", 900)
    preparer = OriginalWindowPreparer(ExtractionConfig(chunk_overlap_chars=0))
    content = "x" * 3000
    chunks = preparer._split_by_chars(content, 1000)
    assert len(chunks) == 3
    assert "".join(chunks) == content


@pytest.mark.asyncio
async def test_row_extraction_uses_observed_task_not_ambient_context():
    from types import SimpleNamespace

    from searchos.harness.middleware.extraction.core.judge import RowExtractor
    from searchos.tools.search_state import _current_task_var

    prompts = []

    class Judge:
        async def ainvoke(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(content="[]")

    state = SearchState(intent="global research objective")
    state.coverage_map.add_table("facts", ["Name", "Value"], primary_key=["Name"])
    extractor = RowExtractor(Judge(), ExtractionConfig())
    token = _current_task_var.set("unrelated ambient task")
    try:
        await extractor.extract_rows(
            [
                {
                    "task_text": "explicit assigned task",
                    "content": "source content",
                    "source_url": "https://example.org/source",
                }
            ],
            state.coverage_map.tables["facts"],
            "",
            state,
            mode="merged",
        )
    finally:
        _current_task_var.reset(token)
    assert "explicit assigned task" in prompts[0]
    assert "unrelated ambient task" not in prompts[0]
