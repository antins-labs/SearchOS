"""轻量研究计划与集合复核；不改变 coverage 或执行预算。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SetScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boundary: str = Field(min_length=1)
    kind: Literal["closed", "open"] = "open"
    table_id: str = ""
    expected_members: list[str] = Field(default_factory=list)
    expected_count: int | None = Field(default=None, ge=0)
    basis_evidence_ids: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: list[Literal["simple", "broad", "deep"]] = Field(min_length=1)
    evidence_obligations: list[str] = Field(min_length=1)
    table_policy: Literal["none", "as_needed"] = "as_needed"
    set_scope: list[SetScope] = Field(default_factory=list)
    stop_rule: str = Field(min_length=1)


def membership_review(state) -> list[dict]:
    """按成员身份比对当前行；数量估计不充当 recall 分母。"""
    from searchos.socm.coverage.projection import answer_evidence
    from searchos.socm.evidence.provenance import evidence_source_urls

    plan = state.research_plan
    if plan is None:
        return []
    available = {n.id for n in answer_evidence(state) if evidence_source_urls(n)}
    reviews = []
    for scope in plan.set_scope:
        tid = scope.table_id
        if not tid and len(state.coverage_map.tables) == 1:
            tid = state.coverage_map.primary_table_id
        table = state.coverage_map.tables.get(tid)
        expected = list(dict.fromkeys(scope.expected_members))
        present = list(table.entities) if table else []
        matched = (
            {name: state.coverage_map.resolve_entity(name, table_id=tid) for name in expected}
            if table
            else {name: None for name in expected}
        )
        linked_basis = bool(scope.basis_evidence_ids) and all(
            eid in available for eid in scope.basis_evidence_ids
        )
        reviews.append(
            {
                "boundary": scope.boundary,
                "kind": scope.kind,
                "table_id": tid,
                "basis_status": "source_linked" if linked_basis else "unverified",
                "basis_evidence_ids": scope.basis_evidence_ids,
                "comparison": "members_compared" if table and expected else "needs_review",
                "missing_members": [
                    name for name, canonical in matched.items() if canonical is None
                ],
                "unexpected_members": [name for name in present if name not in matched.values()]
                if expected
                else [],
                "expected_count_hint": scope.expected_count,
                "known_row_count": len(present) if table else None,
                "count_difference_hint": len(present) - scope.expected_count
                if table and scope.expected_count is not None
                else None,
            }
        )
    return reviews


def render_research_plan(state, *, prompt_for_plan=False) -> str:
    warning = (
        "Coverage measures filling of known rows, not entity recall or factual correctness. "
        "For enumeration, check members against the declared boundary and source evidence "
        "before finishing. A count estimate or equal counts does not prove completeness. "
        "Open sets require search scope and a stop reason; "
        "without completeness evidence, state the limitation."
    )
    if state.research_plan is None:
        return (
            "[Research plan]\n"
            + (
                "Record a concise plan with set_research_plan at the first decision.\n"
                if prompt_for_plan
                else "No recorded plan.\n"
            )
            + warning
        )
    reviews = membership_review(state)
    brief = state.research_plan.model_dump()
    brief["set_scope_status"] = "declared" if brief["set_scope"] else "not_declared"
    if not brief["set_scope"] and state.coverage_map.tables:
        warning += (
            " No set boundary is recorded. If this task requests all members, update set_scope "
            "with the boundary and source-backed inventory before claiming exhaustive coverage."
        )
    for scope in brief["set_scope"]:
        scope["expected_members_count"] = len(scope["expected_members"])
        scope["expected_members"] = scope["expected_members"][:20]
    for row in reviews:
        for key in ("missing_members", "unexpected_members"):
            values = row[key]
            row[key] = values[:20]
            row[key + "_count"] = len(values)
    return (
        "[Research plan]\n"
        + json.dumps(
            {
                **brief,
                "source_mode": (state.source_scope or {}).get("mode", "web"),
                "membership_review": reviews,
            },
            ensure_ascii=False,
        )
        + "\n"
        + warning
    )
