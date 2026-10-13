"""组件消融开关的 CLI、配置与 SOCM 注入边界测试。"""

from argparse import Namespace

from eval.run import _apply_ablation_settings, _build_parser
from searchos.agents.orchestrator.lifecycle import _build_sub_agent_context
from searchos.agents.orchestrator.post_mortem import build_failure_memory_prompt
from searchos.config.settings import settings
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState
from searchos.harness.middleware.extraction import TaskContext
from searchos.harness.middleware.pipelines import web_search_pipeline
from tests.middleware_utils import capture_pipeline
from searchos.socm import FailureMemory, SearchState


def test_eval_cli_parses_independent_component_switches() -> None:
    args = _build_parser().parse_args(
        [
            "--benchmark",
            "widesearch",
            "--no-socm-projection",
            "--no-failure-memory",
            "--no-compress-old-tool-results",
        ]
    )

    assert args.socm_projection is False
    assert args.failure_memory is False
    assert args.compress_old_tool_results is False


def test_eval_cli_leaves_runtime_defaults_untouched_when_omitted() -> None:
    args = _build_parser().parse_args(["--benchmark", "widesearch"])

    assert args.socm_projection is None
    assert args.failure_memory is None
    assert args.compress_old_tool_results is None


def test_apply_ablation_settings_records_effective_values(monkeypatch) -> None:
    monkeypatch.setattr(settings, "enable_socm_projection", True)
    monkeypatch.setattr(settings, "enable_failure_memory", True)
    monkeypatch.setattr(settings, "compress_old_tool_results", True)
    args = Namespace(
        socm_projection=False,
        failure_memory=False,
        compress_old_tool_results=False,
    )

    effective = _apply_ablation_settings(args)

    assert effective == {
        "socm_projection": False,
        "failure_memory": False,
        "compress_old_tool_results": False,
    }
    assert settings.enable_socm_projection is False
    assert settings.enable_failure_memory is False
    assert settings.compress_old_tool_results is False


def test_projection_ablation_removes_initial_role_context(monkeypatch) -> None:
    state = SearchState()
    state.coverage_map.initialize(
        ["Acme"], ["company", "revenue"], primary_key=["company"]
    )
    monkeypatch.setattr(settings, "enable_socm_projection", False)

    assert _build_sub_agent_context(state, agent_type="search_agent") == ""


def test_projection_ablation_short_circuits_per_turn_render(monkeypatch) -> None:
    class _ExplodingWorkspace:
        def load_state(self):
            raise AssertionError("projection-disabled path must not load SOCM")

    monkeypatch.setattr(settings, "enable_socm_projection", False)
    assembly = capture_pipeline(
        monkeypatch, web_search_pipeline, workspace=_ExplodingWorkspace(), task=TaskContext("search"),
        budget=BudgetState(),
    )
    assert not any(isinstance(m, SOCMContextMiddleware) for m in assembly.middleware)
    assert assembly.control.context_snapshot == ""


def test_failure_memory_ablation_suppresses_existing_memories(monkeypatch) -> None:
    state = SearchState()
    state.strategy_log.failure_memories.append(
        FailureMemory(
            failure_class="blocked_source",
            what_failed="The publisher rejected anonymous requests.",
            advice="Use a metadata API.",
            created_at=10**10,
        )
    )
    monkeypatch.setattr(settings, "enable_failure_memory", False)

    assert build_failure_memory_prompt(state, task="Find the paper") == ""
