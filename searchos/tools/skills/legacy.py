"""旧 Executor 的 typed-tool Adapter，保留历史调用与失败语义。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .catalog import _banned_skills_from_state

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
        from searchos.tools.simple_browser.result_pages import show_skill_result
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
