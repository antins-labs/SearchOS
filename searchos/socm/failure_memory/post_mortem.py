"""按任务尝试复盘搜索轨迹；模型只补充有观察支撑的经验。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from searchos.socm.failure_memory.extraction import _SKILL_LIMITS, _SOURCE_LIMITS
from searchos.socm.failure_memory.memory import assigned_task, record_failure, scope_for_task
from searchos.socm.failure_memory.models import FailureKind, FailureMemory, FailureScope
from searchos.socm.failure_memory.prompts import POST_MORTEM_PROMPT

logger = logging.getLogger(__name__)
POST_MORTEM_TIMEOUT_SECONDS = 60.0
_SEARCH_TOOLS = {"search", "local_catalog", "explore_web"}
_READ_TOOLS = {"open", "find", "read_visual", "local_open", "local_find"}
_EXCLUDED_REASONS = {
    "invalid_arguments",
    "malformed_tool_call",
    "model_request_failed",
    "context_limit",
    "extraction_parse_failed",
    "budget_exhausted",
    "user_cancelled",
    "agent_crashed",
    "task_unfinished",
    "no_new_evidence",
    "missing_report",
    "query_repetition",
    "repeated_query",
    "state_stall",
    "research_stalled",
    "zero_cells",
    "no_progress",
}


def _bounded(value: Any, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _trace_calls(messages: Any) -> list[dict]:
    """只保留真实返回的搜索调用；不把调用意图或最终自述作为观察。"""
    pending, calls = {}, {}
    for message in messages or ():
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call.get("id"):
                    pending[call["id"]] = call
            continue
        if not isinstance(message, ToolMessage) or message.tool_call_id not in pending:
            continue
        call = pending[message.tool_call_id]
        name = call.get("name", "")
        if name not in _SEARCH_TOOLS | _READ_TOOLS | {"exec"} and not name.startswith("skill_"):
            continue
        artifact = message.artifact if isinstance(message.artifact, dict) else {}
        execution = artifact.get("execution") or {}
        outcome = artifact.get("outcome") or {}
        execution = execution if isinstance(execution, dict) else {}
        outcome = outcome if isinstance(outcome, dict) else {}
        artifact = {**artifact, "execution": execution, "outcome": outcome}
        if execution.get("started") is False or execution.get("replayed"):
            continue
        if (message.additional_kwargs or {}).get("sf_blocked"):
            continue
        if outcome.get("reason") in _EXCLUDED_REASONS or outcome.get("code") in _EXCLUDED_REASONS:
            continue
        # exec 的宿主回执明确证明启动，参数与加载错误不进入语义复盘。
        if name == "exec" and execution.get("started") is not True:
            continue
        args = call.get("args") or {}
        if not isinstance(args, dict):
            continue
        calls[message.tool_call_id] = {
            "id": message.tool_call_id,
            "tool": name,
            "arguments": args,
            "status": message.status,
            "content": _bounded(message.content),
            "artifact": {
                key: artifact[key]
                for key in (
                    "outcome",
                    "outcomes",
                    "results",
                    "search_results",
                    "page_source",
                    "local_source_metadata",
                    "execution",
                    "pages",
                )
                if key in artifact
            },
        }
    # 同一 checkpoint 消息重现不产生新的观察；保留最近的完整调用。
    selected, size = [], 0
    for call in reversed(list(calls.values())):
        call["artifact"] = json.loads(_bounded_artifact(call["artifact"]))
        length = len(json.dumps(call, ensure_ascii=False, default=str))
        if len(selected) >= 24 or size + length > 24000:
            break
        selected.append(call)
        size += length
    return list(reversed(selected))


def _bounded_artifact(artifact: dict) -> str:
    """保留结构化身份和执行状态，限制长输出对复盘上下文的占用。"""

    def trim(value, depth=0, key=""):
        if isinstance(value, dict):
            return {
                str(name): trim(item, depth + 1, str(name))
                for name, item in list(value.items())[:24]
            }
        if isinstance(value, list):
            return [trim(item, depth + 1, key) for item in value[:8]]
        if isinstance(value, str):
            if key in {"url", "source_url", "source_urls", "ref_id", "query", "q"}:
                # 身份不可按前缀比较；过长则放弃关联，正文仍按原预算截取。
                return value if len(value) <= 4096 else ""
            return value[: 600 if depth > 2 else 1200]
        return value

    return json.dumps(trim(artifact), ensure_ascii=False, default=str)


def _targets(call: dict, kind: FailureKind) -> set[str]:
    args, artifact, name = call["arguments"], call["artifact"], call["tool"]
    if kind == FailureKind.QUERY and name in _SEARCH_TOOLS:
        values = args.get("queries", [args.get("query", args.get("q", ""))])
        return {
            value.strip()
            for value in ([values] if isinstance(values, str) else values)
            if isinstance(value, str) and value.strip()
        }
    if kind == FailureKind.SKILL and (name == "exec" or name.startswith("skill_")):
        from searchos.skills.names import canonical_skill_name

        skill = args.get("skill", name.removeprefix("skill_") if name.startswith("skill_") else "")
        return {canonical_skill_name(skill)} if isinstance(skill, str) and skill else set()
    if kind == FailureKind.SOURCE:
        values = []
        if name in _READ_TOOLS:
            values.extend(args.get(key) for key in ("id_or_url", "url", "ref_id"))
        for key in ("page_source", "local_source_metadata"):
            source = artifact.get(key) or {}
            if isinstance(source, dict):
                values.extend(source.get(key) for key in ("source_url", "ref_id"))
                values.extend(source.get("source_urls") or [])
        for page in artifact.get("pages", []):
            if isinstance(page, dict):
                values.append(page.get("source_url"))
        for item in artifact.get("outcomes", []):
            if isinstance(item, dict) and item.get("tool") in _READ_TOOLS:
                values.append(item.get("source_url"))
        return {
            value
            for value in values
            if isinstance(value, str)
            and value.startswith(("https://", "http://", "local://", "skill://"))
        }
    return set()


def _search_detail(call: dict, query: str) -> dict:
    if call["tool"] == "explore_web":
        for item in call["artifact"].get("outcomes", []):
            if (
                isinstance(item, dict)
                and item.get("tool") in _SEARCH_TOOLS
                and item.get("args", {}).get("query") == query
            ):
                return item.get("outcome", {})
        return {}
    return call["artifact"].get("outcome", {})


def _successful_search(call: dict, query: str) -> bool:
    detail = _search_detail(call, query)
    return (
        call["status"] != "error"
        and isinstance(detail, dict)
        and detail.get("status") in {"success", "empty", "no_results"}
        and not detail.get("error")
        and detail.get("success") is not False
        and (
            "result_count" not in detail
            or type(detail["result_count"]) is int
            and detail["result_count"] >= 0
        )
    )


def _empty_search(call: dict, query: str) -> bool:
    detail = _search_detail(call, query)
    return (
        _successful_search(call, query)
        and not detail.get("result_count")
        and (
            detail.get("status") in {"empty", "no_results"}
            or type(detail.get("result_count")) is int
            and detail["result_count"] == 0
        )
    )


def _candidate_urls(call: dict, query: str) -> set[str]:
    """候选必须属于该查询；批量检索按 query 段或子结果建立关联。"""
    artifact, content = call["artifact"], call["content"]
    if call["tool"] == "explore_web":
        artifact = next(
            (
                item
                for item in artifact.get("outcomes", [])
                if isinstance(item, dict) and item.get("args", {}).get("query") == query
            ),
            {},
        )
        if not any(isinstance(artifact.get(key), list) for key in ("results", "search_results")):
            # 只兼容旧轨迹；新批次的候选身份由宿主结构化返回。
            match = re.search(r"(?m)^## Query \d+: " + re.escape(query) + r"\s*$", content)
            content = (
                re.split(r"\n## Query |\n# Opened pages", content[match.end() :], maxsplit=1)[0]
                if match
                else ""
            )
        else:
            content = ""
    urls = set()
    if not any(isinstance(artifact.get(key), list) for key in ("results", "search_results")):
        urls.update(re.findall(r"(?:https?://|local://)[^\s<>\[\]()\"']+", content))
    for key in ("results", "search_results"):
        results = artifact.get(key, [])
        if isinstance(results, list):
            urls.update(
                item.get("url", item.get("source_url", item.get("ref_id", "")))
                for item in results
                if isinstance(item, dict)
            )
    return {url.rstrip(".,;") for url in urls if isinstance(url, str) and url}


def _read_urls(call: dict) -> set[str]:
    if call["status"] == "error":
        return set()
    if call["tool"] == "explore_web":
        return {
            page["source_url"]
            for page in call["artifact"].get("pages", [])
            if isinstance(page, dict)
            and page.get("source_url")
            and page.get("content")
            and page.get("evidence_eligible") is True
        }
    if call["tool"] not in _READ_TOOLS or not call["content"].strip():
        return set()
    if re.match(r"\s*(?:Error:|\[FETCH_ERROR\]|HTTP [45]\d\d\b)", call["content"], re.I):
        return set()
    source = (
        call["artifact"].get("page_source") or call["artifact"].get("local_source_metadata") or {}
    )
    if not isinstance(source, dict):
        return set()
    detail = call["artifact"].get("outcome") or source.get("access", {})
    if (
        source.get("evidence_eligible") is False
        or source.get("kind") in {"diagnostic", "fixture", "execution_index"}
        or detail.get("error")
        or detail.get("status")
        in {
            "error",
            "failed",
            "blocked",
            "cancelled",
            "timed_out",
        }
    ):
        return set()
    # 纯参数 URL 只说明访问意图；成功阅读需要工具返回的来源身份。
    return {
        source[key]
        for key in ("source_url", "ref_id")
        if isinstance(source.get(key), str) and source[key]
    }


def _source_limit(call: dict, target: str) -> bool:
    if call["tool"] == "explore_web":
        details = [
            item.get("outcome", {})
            for item in call["artifact"].get("outcomes", [])
            if isinstance(item, dict)
            and item.get("tool") in _READ_TOOLS
            and item.get("source_url", item.get("args", {}).get("id_or_url")) == target
        ]
    elif call["tool"] in _READ_TOOLS and target in _targets(call, FailureKind.SOURCE):
        source = call["artifact"].get("page_source", {})
        details = [call["artifact"].get("outcome") or source.get("access", {})]
    else:
        return False
    return any(
        isinstance(detail, dict)
        and detail.get("reason") in _SOURCE_LIMITS
        and detail.get("status") in {"error", "failed", "blocked"}
        for detail in details
    )


def _supported_source(target: str, support: list[dict]) -> bool:
    return any(target in _read_urls(call) or _source_limit(call, target) for call in support)


def _supported_query(query: str, support: list[dict]) -> bool:
    reads = set().union(*(_read_urls(call) for call in support))
    return any(
        query in _targets(call, FailureKind.QUERY)
        and _successful_search(call, query)
        and (_empty_search(call, query) or bool(_candidate_urls(call, query) & reads))
        for call in support
    )


def _supported_path(support: list[dict]) -> bool:
    operations = set()
    for call in support:
        if call["tool"] != "explore_web":
            operations.add((call["tool"], json.dumps(call["arguments"], sort_keys=True).casefold()))
            continue
        # 批处理父调用不是一个搜索步骤；只计实际搜索、已展示阅读和明确负观察。
        for item in call["artifact"].get("outcomes", []):
            if not isinstance(item, dict):
                continue
            args = item.get("args", {})
            query = args.get("query", "")
            if item.get("tool") == "search" and query and _successful_search(call, query):
                operations.add(("search", json.dumps(args, sort_keys=True).casefold()))
        sources = _read_urls(call) | {
            target for target in _targets(call, FailureKind.SOURCE) if _source_limit(call, target)
        }
        operations.update(
            ("open", json.dumps({"id_or_url": url}, sort_keys=True).casefold()) for url in sources
        )
    if len(operations) < 2:
        return False
    for call in support:
        queries = _targets(call, FailureKind.QUERY)
        if any(_empty_search(call, query) for query in queries):
            return True
        if any(_source_limit(call, target) for target in _targets(call, FailureKind.SOURCE)):
            return True
        execution = call["artifact"].get("execution", {})
        if (
            execution.get("started") is True
            and execution.get("package_hash")
            and execution.get("status") in {"error", "failed", "failure"}
            and execution.get("error_type") in _SKILL_LIMITS
        ):
            return True
        candidates = set().union(
            *(_candidate_urls(call, query) for query in queries if _successful_search(call, query))
        )
        candidates.update(_targets(call, FailureKind.SOURCE))
        candidates.update(
            execution.get(key) for key in ("page_url", "index_page_url") if execution.get(key)
        )
        if any(candidates & _read_urls(other) for other in support if other is not call):
            return True
        if call["tool"] == "explore_web" and candidates & _read_urls(call):
            return True
    return False


def _skill_version(target: str, support: list[dict]) -> str:
    executions = [
        call["artifact"].get("execution", {})
        for call in support
        if target in _targets(call, FailureKind.SKILL)
    ]
    if not executions or any(execution.get("started") is not True for execution in executions):
        return ""
    versions = {execution.get("package_hash") for execution in executions}
    return (
        next(iter(versions))
        if len(versions) == 1 and all(isinstance(version, str) and version for version in versions)
        else ""
    )


def _supported_skill(target: str, support: list[dict]) -> bool:
    executions = [call for call in support if target in _targets(call, FailureKind.SKILL)]
    reads = set().union(*(_read_urls(call) for call in support))
    for call in executions:
        execution = call["artifact"].get("execution", {})
        status, reason = execution.get("status"), str(execution.get("error_type", "")).casefold()
        diagnostic = " ".join(str(execution.get(key, "")) for key in ("error", "stderr"))
        if (
            status in {"cancelled", "timed_out", "blocked"}
            or execution.get("timed_out")
            or execution.get("auth_required")
            or re.search(
                r"timeout|timed.?out|network|connection|auth|credential|rate.?limit|cancel|"
                r"validat|argument|permission|budget|not.?loaded",
                reason,
            )
        ):
            return False
        if reason in _SKILL_LIMITS and status in {"error", "failed", "failure"}:
            continue
        products = {
            execution[key]
            for key in ("page_url", "index_page_url")
            if isinstance(execution.get(key), str) and execution[key]
        }
        products.update(_targets(call, FailureKind.SOURCE))
        if (
            status in {"success", "completed", "ok"}
            and execution.get("exit_code", 0) == 0
            and products & reads
        ):
            continue
        # 无类型的 CLI 失败只允许从真实 stderr 判读；已知瞬态与调用错误仍排除。
        if (
            not reason
            and status in {"error", "failed", "failure"}
            and type(execution.get("exit_code")) is int
            and execution["exit_code"] != 0
            and diagnostic.strip()
            and not re.search(
                r"timeout|timed out|network|connection|unauthori|authentic|credentials?|"
                r"rate.limit|cancel|invalid argument|validation|permission denied|HTTP [45]|"
                r"\b(?:401|403|429)\b|forbidden|access denied|\busage:",
                diagnostic,
                re.I,
            )
        ):
            continue
        return False
    return bool(executions)


def _relevant_memories(state: Any, scope: FailureScope) -> list[FailureMemory]:
    from searchos.config.settings import settings

    now = time.time()
    return [
        memory
        for memory in state.failure_memory.records
        if not memory.superseded
        and memory.scope.source_scope_key == scope.source_scope_key
        and now - (memory.last_seen or memory.created_at) < settings.failure_memory_decay_seconds
        and (
            memory.scope == scope
            or (
                memory.kind in {FailureKind.SOURCE, FailureKind.SKILL}
                and not (
                    memory.scope.task_id
                    or memory.scope.table_id
                    or memory.scope.target_cells
                    or memory.scope.entities
                )
            )
        )
    ]


def _parse_records(raw: Any, calls: list[dict]) -> list[tuple[dict, list[dict]]]:
    if isinstance(raw, list):
        raw = "".join(block.get("text", "") for block in raw if isinstance(block, dict))
    if not isinstance(raw, str):
        return []
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)[:-3].strip()
    try:
        values = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(values, list):
        return []
    known, accepted = {call["id"]: call for call in calls}, []
    for item in values[:4]:
        if not isinstance(item, dict):
            continue
        try:
            kind = FailureKind(item.get("kind"))
        except ValueError:
            continue
        fields = {key: item.get(key) for key in ("target", "reason", "what_failed")}
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            continue
        ids = item.get("supporting_call_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(identifier, str) or identifier not in known for identifier in ids)
        ):
            continue
        support = [known[identifier] for identifier in dict.fromkeys(ids)]
        target = fields["target"].strip()
        if kind == FailureKind.PATH:
            if not _supported_path(support):
                continue
        elif target not in set().union(*(_targets(call, kind) for call in support)):
            continue
        if kind == FailureKind.QUERY and not _supported_query(target, support):
            continue
        if kind == FailureKind.SOURCE and not _supported_source(target, support):
            continue
        version = _skill_version(target, support) if kind == FailureKind.SKILL else ""
        if kind == FailureKind.SKILL and (not version or not _supported_skill(target, support)):
            continue
        if fields["reason"].strip() in _EXCLUDED_REASONS:
            continue
        guidance = item.get("guidance", "")
        accepted.append(
            (
                {
                    "kind": kind,
                    "target": fields["target"].strip(),
                    "reason": fields["reason"].strip()[:100],
                    "what_failed": fields["what_failed"].strip()[:600],
                    "guidance": guidance.strip()[:300] if isinstance(guidance, str) else "",
                    "skill_version": version,
                },
                support,
            )
        )
    return accepted


def _observation_ids(task_id: str, agent_id: str, attempt: int, calls: list[dict]) -> list[str]:
    owner = task_id or f"agent:{agent_id}"
    return [f"{owner}:{attempt}:{call['id']}" for call in calls]


def _already_recorded(records: list[FailureMemory], item: dict, observation_ids: list[str]) -> bool:
    return any(
        not memory.superseded
        and memory.kind == item["kind"]
        and memory.target == item["target"]
        and any(
            existing == incoming or existing.startswith(incoming + ":")
            for existing in memory.observation_ids
            for incoming in observation_ids
        )
        for memory in records
    )


async def run_post_mortem(
    *,
    workspace: Any,
    model: Any,
    agent_id: str,
    task_id: str,
    attempt: int,
    report: Any,
    messages: Any,
    trajectory_logger: Any = None,
    scope: FailureScope | None = None,
    task_question: str | None = None,
) -> list[FailureMemory]:
    """失败复盘为尽力补充；取消传播，模型或存储错误不影响搜索结果。"""
    from searchos.config.settings import settings

    if workspace is None or model is None or not settings.enable_failure_memory:
        return []
    calls = _trace_calls(messages)
    if not calls:
        return []
    try:
        state = workspace.load_state()
        task = assigned_task(state, task_id, agent_id)
        scope = scope or scope_for_task(state, task_id, agent_id)
        context = {
            "task_id": task_id,
            "attempt": attempt,
            "target": getattr(task, "question", "") if task_question is None else task_question,
            "report_hint": {
                key: _bounded(getattr(report, key, ""), 800)
                for key in ("result", "last_message", "dead_ends")
            },
            "tool_trace": calls,
            "existing_memories": [
                {
                    "kind": item.kind.value,
                    "target": item.target,
                    "what_failed": item.what_failed,
                    "scope": item.scope.model_dump(),
                }
                for item in _relevant_memories(state, scope)[-20:]
            ],
        }
        response = await asyncio.wait_for(
            model.ainvoke(
                POST_MORTEM_PROMPT.format(context=json.dumps(context, ensure_ascii=False))
            ),
            timeout=POST_MORTEM_TIMEOUT_SECONDS,
        )
        records = []
        for item, support in _parse_records(getattr(response, "content", response), calls):
            ids = _observation_ids(task_id, agent_id, attempt, support)
            existing = _relevant_memories(workspace.load_state(), scope)
            if _already_recorded(existing, item, ids):
                continue
            memory = FailureMemory(
                **item,
                scope=scope,
                task_id=task_id,
                agent_id=agent_id,
                attempt=attempt,
                observation_ids=ids,
                source="post_mortem",
                confidence="low",
                operation=_bounded(
                    [{key: call[key] for key in ("tool", "arguments")} for call in support], 1000
                ),
            )
            stored = record_failure(workspace, memory)
            if stored is not None:
                records.append(stored)
                if trajectory_logger is not None:
                    try:
                        trajectory_logger._append_raw(
                            {
                                "type": "post_mortem_failure_memory",
                                "agent": agent_id,
                                "task_id": task_id,
                                "attempt": attempt,
                                "memory_id": stored.id,
                                "kind": stored.kind.value,
                                "supporting_call_ids": [call["id"] for call in support],
                            }
                        )
                    except Exception:
                        logger.debug("Failure memory trace logging failed", exc_info=True)
        return records
    except Exception:
        logger.debug("Failure memory post-mortem failed for %s", agent_id, exc_info=True)
        return []


def schedule_post_mortem(
    *,
    workspace: Any,
    model: Any,
    pending_tasks: list | None,
    count: list[int] | None,
    agent_id: str,
    task_id: str,
    attempt: int,
    report: Any,
    messages: Any,
    trajectory_logger: Any = None,
) -> None:
    """轨迹与未解线索决定是否复盘；调度器仅传入本次尝试及会话资源。"""
    from searchos.config.settings import settings

    if (
        workspace is None
        or model is None
        or pending_tasks is None
        or not count
        or not settings.enable_failure_memory
        or count[0] >= settings.max_post_mortems_per_session
    ):
        return
    messages = tuple(message.model_copy(deep=True) for message in (messages or ()))
    calls = _trace_calls(messages)
    if not calls:
        return
    negative = any(
        call["status"] == "error"
        or any(_empty_search(call, query) for query in _targets(call, FailureKind.QUERY))
        or call["artifact"].get("outcome", {}).get("status")
        in {"empty", "no_results", "error", "failed"}
        or call["artifact"].get("execution", {}).get("status") in {"failed", "timed_out"}
        for call in calls
    )
    hint = " ".join(str(getattr(report, key, "") or "") for key in ("result", "last_message"))
    unresolved = bool(getattr(report, "dead_ends", None)) or bool(
        re.search(
            r"\bunresolved\b|\bnot found\b|\bno relevant\b|未找到|未能|无法|不覆盖|尚未解决",
            hint,
            re.I,
        )
    )
    if not negative and not unresolved:
        return
    try:
        state = workspace.load_state()
        scope = scope_for_task(state, task_id, agent_id)
        task_question = getattr(assigned_task(state, task_id, agent_id), "question", "")
    except Exception:
        logger.debug("Cannot snapshot failure memory scope", exc_info=True)
        return
    task = asyncio.create_task(
        run_post_mortem(
            workspace=workspace,
            model=model,
            agent_id=agent_id,
            task_id=task_id,
            attempt=attempt,
            report=report,
            messages=messages,
            trajectory_logger=trajectory_logger,
            scope=scope,
            task_question=task_question,
        )
    )
    pending_tasks.append(task)
    count[0] += 1
