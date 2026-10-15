from searchos.agents.orchestrator.prompt import (
    _ADAPTIVE_EXPLORE_ENTRY,
    build_orchestrator_prompt,
)


def test_orchestrator_prompt_balances_recall_and_dispatch_granularity() -> None:
    prompt = build_orchestrator_prompt(
        agent_catalog="agents",
        skill_catalog="skills",
    )

    assert "Choose task count dynamically" in prompt
    assert "Open-set, enumeration, or high-recall tasks" in prompt
    assert "Bounded lookups" in prompt
    assert "Do not split work solely to occupy every slot" in prompt
    assert "at least `free_slots`" not in prompt
    assert "enqueue at least 6 tasks" not in prompt
    assert "silently dropped" not in prompt
    assert "priority desc" not in prompt
    assert "pool.free_slots" not in prompt
    assert "Prefer the fewest high-yield tasks" not in prompt
    assert "usually enqueue 1–3 tasks" not in prompt


def test_orchestrator_prompt_uses_open_world_framing_without_eval_internals() -> None:
    prompt = build_orchestrator_prompt(
        agent_catalog="agents",
        skill_catalog="skills",
    )

    assert "You are an Open-World Search Task Orchestrator" in prompt
    assert "required-columns check (eval mode)" not in prompt
    assert "each required column name must appear verbatim" not in prompt


def test_web_explore_is_optional_and_available_after_search():
    prompt = build_orchestrator_prompt("agents", "skills", source_mode="web")
    prompt = " ".join(prompt.split())
    assert "Explore is optional" in prompt
    assert "New uncertainty during Search" in prompt
    assert "enqueue Explore before calling `check_agents` again" in prompt
    assert "Keep independent Search tasks running" in prompt
    assert "entities explicitly named by the user" in prompt
    assert "very first tool call must be" not in prompt
    assert "re-enqueue once" not in prompt


def test_disabled_explore_reuses_existing_schema_without_fixed_first_call():
    prompt = build_orchestrator_prompt("agents", "skills", enable_explore=False)
    prompt = " ".join(prompt.split())
    assert "Explore is disabled" in prompt
    assert "Reuse and extend existing tables" in prompt
    assert "very first tool call must be" not in prompt


def test_web_and_hybrid_share_adaptive_explore_policy():
    for mode in ("web", "hybrid"):
        prompt = build_orchestrator_prompt("agents", "skills", source_mode=mode)
        assert _ADAPTIVE_EXPLORE_ENTRY in prompt
        disabled = build_orchestrator_prompt(
            "agents", "skills", source_mode=mode, enable_explore=False
        )
        assert _ADAPTIVE_EXPLORE_ENTRY not in disabled


def test_live_follow_ups_avoid_repeated_acknowledgments():
    for mode in ("web", "hybrid"):
        prompt = build_orchestrator_prompt("agents", "skills", source_mode=mode)
        assert "Acknowledge a changed requirement at most once" in prompt
        assert "Tool calls may have empty text content" in prompt
        assert "default wait" in prompt
