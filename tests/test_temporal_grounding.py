"""Temporal grounding stays consistent across planning, research, and extraction."""

from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
from searchos.agents.temporal import render_temporal_grounding
from searchos.harness.middleware.extraction.prompts import build_fill_row_prompt


def test_orchestrator_receives_explicit_temporal_contract():
    prompt = build_orchestrator_prompt(
        agent_catalog="agents",
        skill_catalog="skills",
        current_time="2026-07-10",
    )

    assert "Runtime as-of date: 2026-07-10" in prompt
    assert "hard upper bound" in prompt
    assert "derive a temporal contract" in prompt
    assert "Never send a bare 'latest' task" in prompt


def test_each_sub_agent_role_gets_specialized_temporal_duty():
    search = render_temporal_grounding("2026-07-10", "search_agent")
    explore = render_temporal_grounding("2026-07-10", "explore_agent")
    writer = render_temporal_grounding("2026-07-10", "writer_agent")

    assert "effective period/as-of date" in search
    assert "update cadence" in explore
    assert "mismatched periods" in writer
    assert all("future announcement" in prompt for prompt in (search, explore, writer))


def test_extractor_rejects_temporally_misaligned_values():
    prompt = build_fill_row_prompt(
        global_task="Find the current CEO as of 2026-07-10",
        sub_agent_task="Verify Acme's current CEO",
        primary_key=["Company"],
        data_columns=["CEO"],
        column_desc=None,
        pages=[{"source_url": "https://example.com", "content": "Acme named Jane CEO."}],
        coverage_snapshot="Acme MISSING=[CEO]",
    )

    assert "Runtime as-of date" in prompt
    assert "TEMPORAL FIT IS REQUIRED" in prompt
    assert "publication date is metadata" in prompt
    assert "future target, forecast, schedule" in prompt
