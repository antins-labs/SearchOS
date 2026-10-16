"""技能发现与固定执行工具；旧 typed-tool 仅保留兼容接口。"""

from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


_skill_access_policy_var: ContextVar[dict] = ContextVar("skill_access_policy", default={})


def _skill_allowed(skill) -> bool:
    policy = _skill_access_policy_var.get()
    from searchos.skills.names import canonical_skill_name, canonical_skill_names
    category, name = skill.meta.category.value, canonical_skill_name(skill.meta.name)
    if name in canonical_skill_names(policy.get(f"{category}_deny", ())):
        return False
    only = policy.get("access_only")
    return category != "access" or only is None or name in canonical_skill_names(only)


def _registry():
    from searchos.agents.runtime import _skill_registry_var
    return _skill_registry_var.get()


# Only hide a skill when it's failed repeatedly — a single extraction
# miss could be a transient network / judge hiccup. Plan §6.4 bans "已
# 被证实无效"; one observation doesn't证实.
SKILL_BAN_MIN_OBSERVATIONS = 2


_VALIDATION_ERROR_MARKERS = (
    "missing required parameter",
    "required parameter",
    "missing required",
    "unknown function",
    "invalid function",
    "unsupported function",
    "must be one of",
)


def _is_validation_error(result: dict) -> bool:
    """True when the executor rejected the *call* (bad/missing args / unknown
    function) rather than failing to fetch data. Such errors mean the skill
    never ran — they're a caller bug, not evidence the source is dead, so they
    must not count toward the session-global skill ban.

    Recognises both an explicit ``error_type == "validation"`` (the canonical
    contract) and, for older skills that don't set it, a validation-shaped
    error string.
    """
    if str(result.get("error_type", "")).strip().lower() == "validation":
        return True
    err = result.get("error")
    if not err:
        return False
    err_l = str(err).lower()
    return any(m in err_l for m in _VALIDATION_ERROR_MARKERS)


def _is_failed_result(result: Any) -> bool:
    """使用 Executor 的显式结果状态；空字段不等于检索失败。"""
    return isinstance(result, dict) and not _is_validation_error(result) and bool(
        result.get("error") or result.get("success") is False
        or str(result.get("status", "")).lower() in {"empty", "error", "failed", "no_results"}
    )


def _banned_skills_from_state() -> set[str]:
    """Return skill names flagged as anti-patterns in the current session.

    Plan §6.4 with a guard: only skills with ``observed_count >=
    SKILL_BAN_MIN_OBSERVATIONS`` are hidden. A first-time failure still
    records the AntiPattern (for prompt-level "warn" surface) but
    doesn't yet remove the skill from discovery.
    """
    from searchos.tools.search_state import _workspace_var
    ws = _workspace_var.get()
    if ws is None:
        return set()
    try:
        state = ws.load_state()
    except Exception:
        return set()
    banned: set[str] = set()
    for p in getattr(state.strategy_log, "patterns", []) or []:
        kind = getattr(p.kind, "value", str(p.kind))
        if (kind == "skill" and p.signature
                and p.observed_count >= SKILL_BAN_MIN_OBSERVATIONS):
            banned.add(p.signature)
    return banned


@tool
async def list_skills(category: str = "", availability: str = "", query: str = "", offset: int = 0, limit: int = 5) -> str:
    """Discover skills for your current task, source or missing capability.

    query accepts a natural-language need in any language, an exact skill name,
    or a source domain/URL. Results are ranked candidates with match reasons;
    load_skill to check instructions and limitations before deciding to use one.
    Empty query browses the directory without model selection. No match is fine:
    continue with ordinary web tools. An error is not evidence of no matching skill.

    Args:
        category (str): ``"strategy"`` | ``"access"`` | ``"orchestrator"`` — empty = access + strategy.
        availability (str): ``"enabled"`` | ``"disabled"`` — empty = all.
            The runtime registry contains enabled Skills only.
    """
    from searchos.config.settings import settings
    if not settings.enable_skills:
        return json.dumps({"skills": [], "count": 0, "note": "skill system disabled"})
    reg = _registry()
    if reg is None:
        return json.dumps({"skills": [], "count": 0, "error": "skill registry not bound"})
    banned = _banned_skills_from_state()
    if category and category not in {'access', 'strategy', 'orchestrator'}:
        return json.dumps({'skills': [], 'count': 0, 'error': 'invalid skill category'})
    if len(query) > 2000:
        return json.dumps({'skills': [], 'count': 0, 'error': 'Describe the current retrieval need in at most 2000 characters.'})
    candidates = []
    banned_hits = 0
    for s in reg.list_all():
        if not _skill_allowed(s):
            continue
        if s.meta.name in banned:
            banned_hits += 1
            continue
        if category and s.meta.category.value != category:
            continue
        if availability and s.meta.availability.value != availability:
            continue
        if not category and s.meta.category.value == 'orchestrator':
            continue
        candidates.append(s)
    matches = {}
    if query.strip():
        from searchos.skills.catalog.router import discover_skills
        try:
            ranked = await discover_skills(query, candidates, limit=settings.skill_router_top_k,
                cache=getattr(reg, 'discovery_cache', None), semantic=settings.enable_skill_router)
        except Exception as exc:
            return json.dumps({'skills': [], 'count': 0, 'error': 'skill_discovery_failed',
                'error_type': type(exc).__name__,
                'note': 'Discovery could not complete. Retry later, browse with an empty query, or continue with web tools.'})
        by_name = {s.meta.name: s for s in candidates}
        candidates = [by_name[item['name']] for item in ranked]
        matches = {item['name']: item['reason'] for item in ranked}
    out = [{
            "name": s.meta.name,
            "description": (s.meta.description or s.meta.trigger or "")[:500],
            "package_format": s.package_format,
            "category": s.meta.category.value,
            "availability": s.meta.availability.value,
            "has_executor": s.meta.has_executor,
            "has_scripts": any(resource.startswith("scripts/") for resource in s.resources),
            "trigger": s.meta.trigger,
            "compatibility": s.meta.compatibility,
            **({'match_reason': matches[s.meta.name]} if s.meta.name in matches else {}),
        } for s in candidates]
    start, size = max(0, offset), min(50, max(1, limit))
    return json.dumps(
        {"skills": out[start:start + size], "count": len(out), "banned": banned_hits,
         "next_offset": start + size if start + size < len(out) else None},
        ensure_ascii=False,
    )


@tool
async def load_anti_patterns(skill_name: str, context: str = "") -> str:
    """Return full anti-pattern entries for a Skill.

    Args:
        skill_name (str): name of a skill from ``list_skills``.
        context (str): optional description of the planned or failed attempt;
            when set, entries are reordered by relevance.
    """
    reg = _registry()
    if reg is None:
        return json.dumps({"error": "skill registry not bound"})
    s = reg.get(skill_name)
    if s is None:
        return json.dumps({"error": f"skill {skill_name!r} not found"})

    details = list(getattr(s, "anti_patterns_details", []) or [])
    if not details:
        return json.dumps({
            "skill": skill_name,
            "entries": [],
            "count": 0,
            "note": "no anti-patterns recorded for this skill",
        }, ensure_ascii=False)

    if context.strip():
        from searchos.skills.core.anti_patterns import (
            AntiPatternEntry,
            rank_by_context,
        )
        entries_typed = [
            AntiPatternEntry(
                name=d.get("name", ""),
                summary=d.get("summary", ""),
                what_failed=d.get("what_failed", ""),
                why=d.get("why", ""),
                instead=d.get("instead", ""),
                observed=int(d.get("observed", 1) or 1),
                last_seen=d.get("last_seen", ""),
                source=d.get("source", ""),
            )
            for d in details
        ]
        ranked = rank_by_context(entries_typed, context)
        details = [
            {
                "name": e.name,
                "summary": e.summary,
                "what_failed": e.what_failed,
                "why": e.why,
                "instead": e.instead,
                "observed": e.observed,
                "last_seen": e.last_seen,
                "source": e.source,
            }
            for e in ranked
        ]

    return json.dumps(
        {"skill": skill_name, "entries": details, "count": len(details)},
        ensure_ascii=False, indent=2,
    )


@tool
async def load_skill(skill_name: str) -> str:
    """Read instructions and freeze a skill package for this task before exec."""
    from searchos.tools.skill_execution import load_package
    try:
        return json.dumps(load_package(skill_name), ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def get_skill_tools(skill_names: list[str] | None = None) -> list:
    """Fixed discovery and execution surface; dispatch names are recommendations."""
    from searchos.tools.skill_execution import exec_skill, read_skill_file
    return [list_skills, load_skill, load_anti_patterns,
            exec_skill, read_skill_file]


# ---------------------------------------------------------------------------
# Typed-tool rendering for dispatched access skills
# ---------------------------------------------------------------------------

def render_skill_sets(skill_names: list[str]) -> list:
    """Build typed ``skill_<name>`` tools for the dispatched access skills.

    Only skills the orchestrator named in ``skills=[...]`` become tools;
    everything else stays discoverable via ``list_skills`` / ``load_skill``
    but is not injected. For each name we resolve its manifest through the
    bound ``SkillRegistry`` and keep it only if it declares a
    ``params_schema``.

    Gated by ``enable_skills`` and filtered by the same names as every
    other skill — ``SEARCHOS_SKILL_ONLY`` / ``SEARCHOS_SKILL_EXCLUDE``
    plus the hard ``SKILL_BLACKLIST``.
    """
    from searchos.config.settings import settings
    if not settings.enable_skills or not skill_names:
        return []

    reg = _registry()
    if reg is None:
        return []

    import yaml

    from searchos.skills.catalog.registry import (
        SKILL_BLACKLIST,
        _env_excluded,
        _env_only,
    )
    only = _env_only()                          # None = no whitelist
    excluded = _env_excluded() | set(SKILL_BLACKLIST) | _banned_skills_from_state()

    tools: list = []
    seen: set[str] = set()
    for name in skill_names:
        name = str(name).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if only is not None and name not in only:
            continue
        if name in excluded:
            continue

        skill = reg.get(name)
        if skill is None or not skill.file_path:
            continue
        manifest_path = Path(skill.file_path).parent / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue
        params_schema = data.get("params_schema") if isinstance(data, dict) else None
        if not isinstance(params_schema, dict) or not params_schema:
            continue

        try:
            tool_obj = _make_typed_tool(
                skill_name=name,
                skill_dir=manifest_path.parent,
                description=str(data.get("description") or "").strip(),
                params_schema=params_schema,
            )
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "skipping typed tool for %s: %s", name, e,
            )
            continue
        tools.append(tool_obj)

    return tools


_YAML_TYPE_TO_PY = {
    "string": str,
    "str": str,
    "integer": int,
    "int": int,
    "number": float,
    "float": float,
    "boolean": bool,
    "bool": bool,
    "array": list,
    "list": list,
    "object": dict,
    "dict": dict,
}


def _make_typed_tool(
    *,
    skill_name: str,
    skill_dir: Path,
    description: str,
    params_schema: dict,
):
    """Build one LangChain StructuredTool for a single agent-called skill.

    Steps:
    1. Construct a Pydantic model from ``params_schema`` — field types,
       defaults, and requiredness match the manifest.
    2. Wrap a coroutine that delegates to ``run_executor`` with the
       validated params + the current session's browser / query.
    3. Register the coroutine as a StructuredTool named
       ``skill_<skill_name>`` — this is what the sub-agent calls.
    """
    from langchain_core.tools import StructuredTool
    from pydantic import Field, create_model

    # Build Pydantic model fields
    fields: dict[str, tuple[Any, Any]] = {}
    for param_name, raw_spec in params_schema.items():
        if not isinstance(raw_spec, dict):
            continue
        yaml_type = str(raw_spec.get("type", "string")).strip().lower()
        py_type = _YAML_TYPE_TO_PY.get(yaml_type, str)
        required = bool(raw_spec.get("required", False))
        desc = str(raw_spec.get("description", "")).strip()

        if required:
            fields[param_name] = (py_type, Field(..., description=desc))
        else:
            default = raw_spec.get("default")
            # Distinguish "no default declared" (None) from "default is None":
            # since YAML can't express that subtlety, treat missing `default`
            # as "use the type's zero value" for consistency.
            if default is None:
                default = {
                    str: "",
                    int: 0,
                    float: 0.0,
                    bool: False,
                    list: [],
                    dict: {},
                }.get(py_type)
            fields[param_name] = (py_type, Field(default=default, description=desc))

    if not fields:
        raise ValueError(f"empty params_schema for {skill_name}")

    ParamsModel = create_model(f"{skill_name}_params", **fields)  # type: ignore[call-overload]

    async def _run(**kwargs: Any):
        """执行 skill，将完整结果注册为页面并返回初始视窗。"""
        from searchos.tools.simple_browser.skill_pages import show_skill_result
        def present(result):
            artifact = {}
            content = show_skill_result(skill_name, dict(kwargs), result, artifact=artifact)
            return content, artifact
        # Ban check — mirror list_skills' filtering so skills flagged as
        # AntiPatterns this session can't be called via typed tool either.
        banned = _banned_skills_from_state()
        if skill_name in banned:
            return present({
                "error": f"skill {skill_name!r} has been banned this session "
                         "(repeated failures); try another approach."
            })

        from searchos.agents.orchestrator.lifecycle import _ctx, _record_skill_failure
        from searchos.skills.runtime.legacy.executor_runtime import run_executor

        query = ""
        if _ctx.workspace is not None:
            try:
                query = _ctx.workspace.load_state().intent or ""
            except Exception:
                pass

        result = await run_executor(
            skill_dir,
            dict(kwargs),
            query=query,
        )

        # Failure signal = the executor's own verdict. Evidence is extracted
        # asynchronously by the middleware (batched flush), so an evidence-count
        # delta can't be measured synchronously here — using it would record a
        # false failure on every call and ban working skills.
        #
        # Input-validation errors (bad/missing args) mean the executor never
        # ran — the skill never touched the network. Counting them toward the
        # session ban lets a malformed-call loop poison a working source for
        # every agent (the www_universityrankings_ch regression). Only genuine
        # run-time failures (network / no-evidence) count.
        if _is_failed_result(result):
            _record_skill_failure(skill_name, dict(kwargs))
            result = dict(result)
            result["recovery_hint"] = (
                "This skill is now disabled for this session after repeated empty/failed results. "
                "Use another source or search, then open the original page."
                if skill_name in _banned_skills_from_state() else
                "No usable result. Change the query or source; repeated failures disable this skill for the session."
            )

        return present(result)

    tool_description = description or f"Agent-called skill: {skill_name}"
    tool_description += (
        "\nReturns the initial viewport of a saved result page. "
        "Use open(the skill:// URL, loc=...) and find(pattern) to read more; "
        "opening the saved page does not rerun this skill."
    )
    # Document the shape that ends up in the sub-agent's tool list.
    params_doc = "\n".join(
        f"- {pname}: {params_schema[pname].get('description', '').strip()}"
        for pname in params_schema
        if isinstance(params_schema[pname], dict)
    )
    if params_doc:
        tool_description = f"{tool_description}\n\nParameters:\n{params_doc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=f"skill_{skill_name}",
        description=tool_description,
        args_schema=ParamsModel,
        response_format="content_and_artifact",
    )
