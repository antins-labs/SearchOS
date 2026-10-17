"""由现有 Orchestrator 决策保存计划，不额外调用分类模型。"""

import json

from langchain_core.tools import tool
from pydantic import ValidationError

from searchos.socm.planning.research_plan import ResearchPlan, membership_review


@tool
async def set_research_plan(plan_json: str) -> str:
    """Save a concise plan in the first decision; update only when scope or evidence changes.

    plan_json is an object with strategy (array of simple/broad/deep; combinable),
    evidence_obligations (short concrete requirements), table_policy (none/as_needed),
    stop_rule (what evidence suffices), and optional set_scope (array).
    Each scope has boundary, kind (closed/open), optional table_id, expected_members
    (canonical row keys), expected_count (hint only), basis_evidence_ids (actual active
    facts establishing membership). Leave unknown members/count absent. A guessed list
    is tentative, not a completion standard. Source mode and budgets remain runtime-owned.
    Read inspect_table for full member comparison; source_linked means traceable, not verified.
    """
    from searchos.agents.runtime import _ctx
    from searchos.socm.coverage import answer_evidence
    from searchos.socm.evidence.provenance import evidence_source_urls

    if _ctx.workspace is None:
        return "Error: workspace not initialized"
    try:
        plan = ResearchPlan.model_validate_json(plan_json)
    except (ValueError, ValidationError) as exc:
        return f"Error: invalid research plan: {exc}"

    def apply(state):
        available = {n.id for n in answer_evidence(state) if evidence_source_urls(n)}
        unknown = {
            eid
            for scope in plan.set_scope
            for eid in scope.basis_evidence_ids
            if eid not in available
        }
        if unknown:
            raise ValueError(
                "Membership basis must cite active facts with original sources: "
                + ", ".join(sorted(unknown))
            )
        state.research_plan = plan
        return state

    try:
        state = _ctx.workspace.atomic_update_state(apply)
    except ValueError as exc:
        return f"Error: {exc}"
    return json.dumps(
        {"plan": plan.model_dump(), "membership_review": membership_review(state)},
        ensure_ascii=False,
    )
