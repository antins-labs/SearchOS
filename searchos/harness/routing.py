"""Select an execution path while the shared runtime enforces source permissions."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from searchos.socm.planning.research_plan import ResearchPlan
from searchos.utils.json_extract import extract_json_object


class SearchRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Literal["simple", "research"]
    reason: str = Field(min_length=1, max_length=600)
    evidence_obligations: list[str] = Field(min_length=1)
    strategy: list[Literal["simple", "broad", "deep"]] = Field(min_length=1)
    table_policy: Literal["none", "as_needed"] = "as_needed"

    @model_validator(mode="after")
    def constrain_simple(self):
        if self.path == "simple":
            self.strategy = ["simple"]
            self.table_policy = "none"
        return self

    def plan(self) -> ResearchPlan:
        if self.path == "simple":
            stop_rule = """Resolve every stated obligation using original source evidence. When search time expires, stop retrieval and summarize supported findings and unresolved requirements in the current conversation."""
        else:
            stop_rule = """Check the stated obligations and any declared set boundary against evidence; report unresolved gaps and the stopping reason."""
        return ResearchPlan(
            strategy=self.strategy,
            evidence_obligations=self.evidence_obligations,
            table_policy=self.table_policy,
            stop_rule=stop_rule,
        )


def research_route(query: str, reason: str) -> SearchRoute:
    return SearchRoute(
        path="research", reason=reason, evidence_obligations=[query],
        strategy=["deep"], table_policy="as_needed",
    )


_ROUTER_PROMPT = """# Role
You are the SearchOS query router. Select the least involved workflow that can deliver a complete,
source-supported answer. Classify the request without searching or answering it.
The user message supplies the question and source_mode. Apply these rules to that input;
local mode permits only the authorized local sources.

# Decision rubric
Identify the requested deliverable and its completion check. Evaluate two criteria independently:

1. Coverage: How will the agent know that all requested cases have been covered?
   - Direct: one agent can check a specific fact, the given targets, or all entries in a source
     that defines the requested population. Completion follows from those checks.
   - Broad: the agent must discover candidates and verify eligibility or omissions, or track
     separate investigations that exceed one short search. State how coverage would be established.
2. Inference: What connects the evidence to the requested conclusion?
   - Direct: sources state the answer or supply inputs for an unambiguous operation such as a
     calculation, comparison of like measures, or application of a stated rule.
   - Deep: the agent must establish a comparison standard, reconcile material contradictions,
     test competing explanations, or weigh evidence to justify a new conclusion. State which
     judgment the evidence must support.

# Decision rule
- Both direct: path=simple, strategy=["simple"]. One search agent can recognize completion.
- Broad only: path=research, strategy=["broad"]. Deep only: path=research, strategy=["deep"].
- Both broad and deep: path=research, strategy=["broad","deep"]. Both obligations must be present.
- Only research can create or populate a research table schema. If explicitly required, select
  research and table_policy=as_needed; use broad for assembling rows when both criteria are direct.
  A request to display results as a table can still use simple.
Judge the work under the requested scope and source constraints. Do not assume a comprehensive
source exists or add hypothetical complications. Following links and using a skill can be routine.
Item counts and question words alone decide neither criterion.

# Calibration: same subject, different deliverables
- Read closure dates for every site in a specified bulletin: simple. The bulletin bounds the list.
- Find every affected site across independently issued closure notices: broad. Check the roster for omissions.
- Determine why one site closed when two notices give incompatible reasons: deep. Test both accounts.
- Find every affected site and resolve conflicting explanations for their closures: broad and deep.

# Output
Return exactly one JSON object. Example for the first calibration request:
{"evidence_obligations":["Verify the closure date for each site listed in the bulletin."],
 "reason":"Checking each bulletin entry establishes all requested dates.",
 "path":"simple","strategy":["simple"],"table_policy":"none"}

Field requirements:
- evidence_obligations: a nonempty array of short strings covering the facts or judgments to verify.
  Preserve the user's scope and leave factual values open.
- reason: one sentence naming the source check that completes simple, or the coverage or inference
  work that requires research. For a mixed strategy name both.
- path and strategy: use the values and array forms in the decision rule.
- table_policy: "none" for simple; for research use "as_needed" when a table is requested or helps
  track entities and attributes, otherwise "none"."""


async def select_route(*, model, query, state, execution_path="auto", follow_up=False,
                       fixed_schema=False, targeted_repair=False, table_export=False,
                       remaining_time_s=None, trajectory_logger=None):
    """Honor structural constraints and fall back to research on classifier errors."""
    started = time.monotonic()
    source_mode = (state.source_scope or {}).get("mode", "web")
    reason = ""
    if execution_path == "unified":
        reason = "unified_control"
    elif fixed_schema or state.required_attributes or targeted_repair or table_export:
        reason = "structured_or_repair_workflow"
    elif (follow_up or state.coverage_map.tables or state.frontier.questions
          or state.evidence_graph.node_count):
        reason = "continue_existing_research"
    elif source_mode not in {"web", "local"}:
        reason = "multiple_source_workflow"
    elif remaining_time_s is not None and remaining_time_s <= 1:
        reason = "session_budget_exhausted"

    if reason:
        route = research_route(query, reason)
    else:
        timeout = min(30.0, remaining_time_s) if remaining_time_s is not None else 30.0
        try:
            if trajectory_logger is not None:
                trajectory_logger.log_generation_started(agent="orchestrator", phase="routing")
            response = await asyncio.wait_for(model.ainvoke([
                SystemMessage(content=f"""{_ROUTER_PROMPT}

# Runtime context
Runtime as-of date: {date.today().isoformat()}. Use this date to interpret relative dates and apply any explicit user cutoff. Plan verification for recent events using sources available under source_mode."""),
                HumanMessage(content=json.dumps({
                    "question": query, "source_mode": source_mode,
                }, ensure_ascii=False)),
            ], config={"run_name": "search_router", "tags": ["search_router"]}), timeout)
            content = response.content
            if isinstance(content, list):
                content = "\n".join(
                    block.get("text", "") for block in content if isinstance(block, dict)
                )
            route = SearchRoute.model_validate(extract_json_object(str(content)) or {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            route = research_route(query, f"router_fallback:{type(exc).__name__}")

    if trajectory_logger is not None:
        trajectory_logger._append_raw({
            "type": "harness", "kind": "search_route", "execution_path": execution_path,
            **route.model_dump(), "elapsed_s": round(time.monotonic() - started, 3),
        })
    return route
