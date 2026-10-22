"""从可信工具元数据提取局部搜索经验；正文和停滞次数不作失败判据。"""

from __future__ import annotations

from typing import Any

from searchos.socm.failure_memory.models import FailureKind, FailureMemory, FailureScope
from searchos.socm.planning.retry_routes import route_signature

# 暂时超时、限流和服务端异常不能证明来源或技能不适用。
_SOURCE_LIMITS = {
    "auth_required",
    "access_denied",
    "paywall",
    "blocked",
    "http_401",
    "http_403",
    "http_404",
    "http_410",
    "unsupported_content_type",
}
_SKILL_LIMITS = {
    "schema_changed",
    "parse_error",
    "unsupported_operation",
    "capability_unavailable",
    "endpoint_removed",
    "invalid_result",
    "missing_dependency",
    "dependency_missing",
}


def extract_tool_failures(
    tool: str,
    args: dict,
    result: Any,
    *,
    observation_id: str,
    scope: FailureScope,
    task_id: str = "",
    agent_id: str = "",
    attempt: int = 0,
) -> list[FailureMemory]:
    """明确事实直接提取；跨操作的搜索路径判断交给 post-mortem。"""
    artifact = getattr(result, "artifact", None)
    if not isinstance(artifact, dict) or not isinstance(args, dict):
        return []
    context = dict(
        scope=scope, task_id=task_id, agent_id=agent_id, attempt=attempt, confidence="high"
    )
    execution = artifact.get("execution", {})
    if isinstance(execution, dict) and (
        execution.get("started") is False or execution.get("replayed")
    ):
        return []
    if tool == "explore_web":
        records = []
        for item in artifact.get("outcomes", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            records.extend(
                _extract_observation(
                    item.get("tool", ""),
                    item.get("args", {}),
                    item.get("outcome", {}),
                    item.get("source_url", ""),
                    f"{observation_id}:{item['id']}",
                    context,
                )
            )
        return records
    if tool == "exec" or tool.startswith("skill_"):
        if not isinstance(execution, dict) or execution.get("started") is not True:
            return []
        reason = execution.get("error_type", "")
        version = execution.get("package_hash", "")
        if (
            reason not in _SKILL_LIMITS
            or not version
            or execution.get("status") not in {"error", "failed", "failure"}
        ):
            return []
        target = str(args.get("skill", "")) if tool == "exec" else tool.removeprefix("skill_")
        if not target:
            return []
        from searchos.skills.names import canonical_skill_name

        return [
            FailureMemory(
                kind=FailureKind.SKILL,
                target=canonical_skill_name(target),
                reason=reason,
                what_failed=str(execution.get("error") or execution.get("stderr") or reason)[:2000],
                operation=route_signature(tool, args),
                skill_version=version,
                observation_ids=[observation_id],
                **context,
            )
        ]
    source = artifact.get("page_source", {})
    source = source if isinstance(source, dict) else {}
    return _extract_observation(
        tool,
        args,
        artifact.get("outcome", source.get("access", {})),
        source.get("source_url", ""),
        observation_id,
        context,
    )


def _extract_observation(
    tool: str, args: dict, detail: Any, source_url: str, observation_id: str, context: dict
) -> list[FailureMemory]:
    if not isinstance(detail, dict) or not isinstance(args, dict):
        return []
    if tool in {"search", "local_catalog"}:
        query = args.get("query", "")
        if (
            not isinstance(query, str)
            or not query.strip()
            or detail.get("status") != "success"
            or type(detail.get("result_count")) is not int
            or detail["result_count"] != 0
            or detail.get("error")
        ):
            return []
        conditions = {
            key: detail[key] for key in ("search_provider", "max_results") if key in detail
        }
        return [
            FailureMemory(
                kind=FailureKind.QUERY,
                target=query.strip(),
                reason="empty_result",
                what_failed=(
                    "Search completed with no candidates under the recorded search conditions."
                ),
                operation=route_signature(tool, {**args, **conditions}),
                observation_ids=[observation_id],
                **context,
            )
        ]
    reason = detail.get("reason", "")
    if (
        tool not in {"open", "read_visual"}
        or reason not in _SOURCE_LIMITS
        or detail.get("status") not in {"error", "failed", "blocked"}
        or not isinstance(source_url, str)
        or not source_url.startswith(("http://", "https://"))
    ):
        return []
    operation_args = {**args, "id_or_url": source_url} if tool == "open" else args
    return [
        FailureMemory(
            kind=FailureKind.SOURCE,
            target=source_url,
            reason=reason,
            what_failed=f"This access method could not read the source: {reason}.",
            operation=route_signature(tool, operation_args),
            observation_ids=[observation_id],
            **{
                **context,
                "scope": FailureScope(source_scope_key=context["scope"].source_scope_key),
            },
        )
    ]
