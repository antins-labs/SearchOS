from searchos.agents.orchestrator.prompt import build_orchestrator_prompt


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
    assert "Explore is optional" in prompt
    assert "multi-attribute lookups" in prompt
    assert "New uncertainty during Search" in prompt
    assert "enqueue Explore before\n  calling `check_agents` again" in prompt
    assert "Keep\n  independent Search tasks running" in prompt
    assert "entities explicitly named by the user" in prompt
    assert "very first tool call must be" not in prompt
    assert "re-enqueue once" not in prompt


def test_disabled_explore_reuses_existing_schema_without_fixed_first_call():
    prompt = build_orchestrator_prompt("agents", "skills", enable_explore=False)
    assert "Explore is disabled" in prompt
    assert "Reuse and\nextend existing tables" in prompt
    assert "very first tool call must be" not in prompt
