"""验证网页装配规则与实际 graph 挂载一致。"""

from types import SimpleNamespace

import pytest

from searchos.config.middleware import CATALOG, PIPELINES, available, default_selection
from searchos.config.settings import settings
from searchos.harness.middleware import TaskContext
from searchos.harness.middleware import pipelines
from tests.middleware_utils import capture_pipeline


@pytest.fixture(autouse=True)
def clean_selection(monkeypatch):
    monkeypatch.setattr(settings, "middleware_pipelines", {})


@pytest.mark.parametrize("pipeline", PIPELINES)
@pytest.mark.parametrize("flags", [False, True])
def test_default_preview_matches_actual_mount_order(monkeypatch, pipeline, flags):
    for field in ("enable_socm_projection", "use_layered_context", "compress_old_tool_results"):
        monkeypatch.setattr(settings, field, flags)
    options = {"workspace": None}
    if pipeline != "orchestrator":
        options["task"] = TaskContext("test")
    graph = capture_pipeline(monkeypatch, getattr(pipelines, f"{pipeline}_pipeline"), **options)
    unavailable = {"SteeringMiddleware", "StateStallMiddleware", "ProgressGuardMiddleware",
                   "WebEvidenceMiddleware", "LocalEvidenceMiddleware", "FinalSummaryEvidenceMiddleware"}
    assert [type(item).__name__ for item in graph.middleware] == [
        name for name in default_selection(pipeline, settings) if name not in unavailable
    ]


@pytest.mark.parametrize("pipeline", PIPELINES)
def test_empty_selection_disables_all_business_middleware(monkeypatch, pipeline):
    monkeypatch.setattr(settings, "middleware_pipelines", {pipeline: []})
    options = {"workspace": None}
    if pipeline != "orchestrator":
        options["task"] = TaskContext("test")
    graph = capture_pipeline(monkeypatch, getattr(pipelines, f"{pipeline}_pipeline"), **options)
    assert graph.middleware == []


def test_explicit_selection_enables_optional_components_despite_legacy_flags(monkeypatch):
    monkeypatch.setattr(settings, "enable_socm_projection", False)
    monkeypatch.setattr(settings, "compress_old_tool_results", False)
    monkeypatch.setattr(settings, "use_layered_context", False)
    selected = ["ToolHistoryMiddleware", "SOCMContextMiddleware", "SearchEpisodeMiddleware"]
    monkeypatch.setattr(settings, "middleware_pipelines", {"web_search": selected, "local_search": selected[:2]})
    for pipeline, expected in [("web_search", selected), ("local_search", selected[:2])]:
        graph = capture_pipeline(monkeypatch, getattr(pipelines, f"{pipeline}_pipeline"), workspace=None, task=TaskContext("test"))
        assert [type(item).__name__ for item in graph.middleware] == expected


def test_runtime_conditions_still_gate_selected_components(monkeypatch):
    from searchos.harness.middleware.extraction import InMemoryEvidenceStore
    from searchos.socm import SearchState

    workspace = InMemoryEvidenceStore(SearchState())
    selected = ["FinalSummaryEvidenceMiddleware", "WebEvidenceMiddleware", "ProgressGuardMiddleware", "ToolProgressMiddleware"]
    monkeypatch.setattr(settings, "middleware_pipelines", {"web_search": selected})
    for model, final_summary, expected in [
        (None, True, ["ToolProgressMiddleware"]),
        (object(), False, ["WebEvidenceMiddleware", "ProgressGuardMiddleware"]),
        (object(), True, selected[:-1]),
    ]:
        graph = capture_pipeline(monkeypatch, pipelines.web_search_pipeline, workspace=workspace,
                                 task=TaskContext("test"), extraction_model=model, final_summary=final_summary)
        assert [type(item).__name__ for item in graph.middleware] == expected
        conditions = {"extraction_model": model is not None, "final_summary": final_summary}
        catalog = {item["id"]: item for item in CATALOG}
        assert [name for name in selected if all(
            conditions[key] == value for key, value in catalog[name]["requirements"].items()
        )] == expected


def test_compaction_uses_agent_model_and_requires_known_window(monkeypatch):
    from searchos.agents import runtime
    monkeypatch.setattr(settings, "middleware_pipelines", {"writer": ["CompactionContextMiddleware"]})
    monkeypatch.setattr(runtime, "create_search_agent_graph", lambda **args: SimpleNamespace(**args))
    for profile, count in [(None, 0), ({"max_input_tokens": 32000}, 1)]:
        model = SimpleNamespace(profile=profile)
        graph = pipelines.writer_pipeline(model, [], workspace=None, task=TaskContext("test"))
        assert len(graph.middleware) == count
        if count:
            assert graph.middleware[0].model is model


def test_catalog_describes_real_hooks_and_covers_available_components():
    from langchain.agents.middleware import AgentMiddleware
    from searchos.harness import middleware
    from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware

    catalog = {item["id"]: item for item in CATALOG}
    assert len(catalog) == len(CATALOG)
    for pipeline in PIPELINES:
        assert set(available(pipeline)) <= catalog.keys()
    for name, item in catalog.items():
        cls = SteeringMiddleware if name == "SteeringMiddleware" else getattr(middleware, name)
        hooks = [hook for hook in ("before_agent", "before_model", "after_model", "after_agent", "wrap_model_call", "wrap_tool_call")
                 if getattr(cls, f"a{hook}") is not getattr(AgentMiddleware, f"a{hook}")]
        assert set(item["hooks"]) == set(hooks), name
