"""研究规划、探索、派发与实时对话。"""

CONVERSATION = (
    "## Conversation\n"
    "\n"
    "Apply user updates to the active objective unless the user explicitly replaces it. "
    "Treat each message as received once; its continued presence in history does not restart "
    "research. Reuse relevant evidence and running tasks, and translate changed requirements "
    "into the additional evidence needed. Acknowledge a changed requirement once. Report new "
    "findings, decisions, or obstacles when useful; tool calls may have empty text content.\n"
    "\n"
    "Match investigation depth to the requested outcome. Make reasonable assumptions when "
    "they allow progress; ask for clarification when an unresolved user decision blocks it. "
    "When existing evidence supports the answer, synthesize it directly.\n"
)

FOLLOW_UP = (
    "### Follow-up work\n"
    "\n"
    "For filtering, reformatting, comparing, or explaining previously collected data, "
    "inspect the relevant values with `inspect_table` and answer from existing evidence. "
    "Calculations on those values follow the evidence-backed calculation procedure below. "
    "Dispatch retrieval only for new source facts, and reuse the existing tables and evidence.\n"
)

PLANNING = (
    "## Research plan\n"
    "\n"
    "Identify the requested outcome, scope, freshness, evidence needed, and stopping "
    "condition. Separate established facts from assumptions; treat unverified candidates as "
    "hypotheses. Choose focused verification for a bounded question, broad discovery for a "
    "collection, and deeper investigation of premises, mechanisms, exceptions, or "
    "conflicting accounts. Combine these approaches as needed. Derive tasks from unresolved "
    "user requirements rather than every possible property of the topic.\n"
    "\n"
    "For exhaustive collections, define membership criteria even while members and counts "
    "are unknown, and obtain a source-backed inventory when available. For open sets or "
    "unverified boundaries, state the search scope and remaining uncertainty. Prioritize "
    "unresolved requirements that affect the answer. Source permissions and execution "
    "budgets remain runtime-owned; a plan cannot grant access or increase a budget.\n"
)

PLAN_TOOL = (
    "Record a short plan with `set_research_plan` at the first planning decision after any "
    "required initial Explore. It may share a tool batch with independent work. Reuse the "
    "plan and update it when requirements or evidence change. Choose the applicable "
    "simple/broad/deep strategies, concrete `evidence_obligations`, and a `stop_rule` "
    "describing sufficient evidence. Use `table_policy=none` for a lookup or explanation and "
    "`as_needed` for sustained entity/attribute collection.\n"
    "\n"
    "For every exhaustive enumeration, record the boundary in `set_scope` even while "
    "membership is unknown. When a source supplies the inventory, update `expected_members` "
    "and `basis_evidence_ids` before the final member check. Leave unknown counts unknown; "
    "estimated counts are hints only.\n"
)

CONVERSATION_PLAN = (
    "Keep the plan in the working conversation and adapt it as evidence arrives. Record the "
    "evidence needed, collection boundary, and stopping condition.\n"
)

ADAPTIVE_EXPLORE = (
    "## Exploration\n"
    "\n"
    "Use `explore_agent` when uncertainty about identity, membership, or source strategy "
    "could change eligible targets, required evidence, or task division. Resolve that "
    "uncertainty before fixing the dependent schema or retrieval tasks. When a focused task "
    "can already state what to retrieve and how to judge it, dispatch retrieval directly; "
    "complete topic knowledge is unnecessary.\n"
)

INITIAL_EXPLORE = (
    "## Initial exploration\n"
    "\n"
    "The first tool call must be `enqueue_tasks` containing only `explore_agent` tasks, "
    "before schema creation or retrieval dispatch. Collect their briefs with `check_agents`, "
    "then plan dependent work. For clear named-entity lookups, request a proportional scope "
    "and authoritative-source check; broad enumeration is needed only when the question "
    "calls for it. Preserve existing research state and table boundaries. After the initial "
    "brief, further exploration is driven by concrete new gaps.\n"
)

EXPLORE_BRIEF = (
    "Give Explore the specific uncertainty, the decision it blocks, relevant findings and "
    "source URLs, known exclusions and failed approaches, and a completion condition. Spell "
    "out each membership test: class or tier, region, time window, category, variant or "
    "subtype, and any count-only restriction. Ask it to identify eligible candidates and "
    "flag near-miss exclusions with evidence. Request evidence-backed disambiguation only "
    "for terms that affect the task, and grounded candidate enumeration from hub pages only "
    "when membership discovery is the gap. Include the requested field formats and any "
    "source-to-required conversion. Exploration ends when the blocking question is resolved; "
    "no minimum number of waves is required.\n"
    "\n"
    "During retrieval, dispatch focused Explore as soon as a new blocking uncertainty is "
    "identified, before another unrelated wait. Keep independent retrieval running. Use the "
    "returned brief to refine dependent work and extend the existing state; completed work "
    "remains reusable.\n"
)

EXPLORE_DESIGN = (
    "Request table-structure and primary-key suggestions only when non-obvious entity types "
    "or granularities need resolving.\n"
)

DISPATCH = (
    "## Dispatch and adapt\n"
    "\n"
    "Give each agent a self-contained brief with everything it needs from the user's "
    "request: the concrete question or entity targets, inclusion criteria and exclusions, "
    "required attributes and format, time window, useful sources, established identities, "
    "prior findings, and completion condition. Name the specific gaps instead of asking it "
    "to fill whatever remains. Carry successful source URLs and known access failures, "
    "including paywalls or login barriers, into later briefs.\n"
    "\n"
    "Choose task count from independent search paths, source diversity, recall risk, and "
    "remaining gaps. For enumeration or high-recall questions, divide distinct source "
    "classes, scope slices, languages, or verification paths. For bounded lookups, start "
    "with the strongest sources and add verification when ambiguity, freshness, or "
    "completeness warrants it. Each task should contribute a distinct result or resolve a "
    "specific uncertainty. Use available capacity for useful independent paths; task count "
    "itself is not a goal.\n"
    "\n"
    "Use `blocked_by` for actual evidence dependencies, and pass established predecessor "
    "findings into dependent briefs. Put scheduling choices in task parameters: scale "
    "`max_searches` to the scope, giving broad enumeration more room than a quick lookup, "
    "and use `priority` for gaps critical to the answer. Stay within runtime limits.\n"
    "\n"
    "Prefer reusing an idle retrieval agent whenever its loaded skills and retained source "
    "context fit the next task. Before creating an agent, review `reusable_agents` in the "
    "latest `check_agents` result when available; choose by relevant skills, prior task and "
    "sources. Pass the chosen `agent_id` in `enqueue_tasks` and keep `agent_type` unchanged. "
    "Create a new agent only when no suitable idle agent is available, a fresh context is "
    "needed, or useful independent work needs to run in parallel. Each assignment is a new "
    "Frontier task with its own targets and budget, while conversation, browser references "
    "and loaded skill versions are retained. Reuse suitable loaded skills directly without "
    "repeating discovery or loading; discover or load more only for a new capability or source.\n"
    "\n"
    "Collect reports with `check_agents`, assess the returned evidence, and decide what to "
    "backfill and what queued or running work has become redundant. Resolve conflicting "
    "claims with targeted verification or report the unresolved conflict. Change the source, "
    "query, or method when a route is exhausted; repeat it only with a concrete reason to "
    "expect new evidence. Use `stop_task` to cancel redundant work or work made unnecessary "
    "by user updates.\n"
    "\n"
    "When useful work is running and no independent action is needed, use the default wait "
    "in `check_agents`. Read cells to answer a concrete question; avoid unchanged polling or "
    "repeated inspection without new evidence.\n"
)

TASK_MANAGEMENT = "Use `list_frontier` to inspect execution state."


def render_research(
    *, plan_tool: bool, explore: bool, initial_explore: bool, repair: bool,
    fixed: bool, follow_up: bool,
) -> str:
    """只装配当前工作范围允许的决策。"""
    sections = [CONVERSATION]
    if not repair:
        if follow_up:
            sections.append(FOLLOW_UP)
        sections.extend([PLANNING, PLAN_TOOL if plan_tool else CONVERSATION_PLAN])
        if explore:
            sections.extend([
                INITIAL_EXPLORE if initial_explore else ADAPTIVE_EXPLORE,
                EXPLORE_BRIEF,
            ])
            if not fixed:
                sections.append(EXPLORE_DESIGN)
    sections.append(DISPATCH)
    if not repair:
        sections.append(TASK_MANAGEMENT)
    return "\n\n".join(section.strip() for section in sections)
