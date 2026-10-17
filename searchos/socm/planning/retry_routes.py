"""任务级重试路线：记录已尝试查询和来源，派发后在工具入口强制换路。"""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit


def query_family(query: str) -> str:
    # 忽略大小写、标点和词序；不声称能识别语义改写。
    return " ".join(sorted(re.findall(r"\w+", query.casefold())))


def source_family(url: str) -> str:
    host = (urlsplit(url if "://" in url else "https://" + url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def call_routes(tool: str, args: dict) -> tuple[list[str], list[str]]:
    queries, families = [], []
    if tool in {"search", "local_catalog", "explore_web"}:
        values = args.get("queries", [args.get("query", "")])
        if isinstance(values, str):
            values = [values]
        for query in values:
            if isinstance(query, str) and query.strip():
                queries.append(query)
                families.extend(
                    source_family(host)
                    for host in re.findall(r"(?<!-)\bsite:([^\s]+)", query, flags=re.I)
                )
    if tool == "exec" and args.get("skill"):
        from searchos.skills.names import canonical_skill_name
        families.append("skill:" + canonical_skill_name(str(args["skill"])))
    if tool.startswith("skill_"):
        families.append("skill:" + tool.removeprefix("skill_"))
    if tool in {"open", "read_visual"}:
        url = args.get("id_or_url", args.get("url", ""))
        if str(url).isdigit():
            from searchos.tools.simple_browser.state import _get_browser

            browser = _get_browser()
            for key in reversed(browser.page_stack):
                page = browser.pages.get(key)
                if page is not None and str(url) in page.urls:
                    url = page.urls[str(url)]
                    break
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            families.append(source_family(url))
    if tool == "find":
        from searchos.tools.simple_browser.state import _get_browser, _get_source_page

        browser = _get_browser()
        if browser.has_pages:
            url = _get_source_page(browser).url
            if url.startswith(("http://", "https://")):
                families.append(source_family(url))
    if tool in {"local_open", "local_find"}:
        path = str(args.get("ref_id", args.get("path", args.get("document_id", ""))))
        if path:
            document = urlsplit(path).netloc if path.startswith("local://") else path
            families.append("local:" + document)
    return queries, list(dict.fromkeys(families))


def retry_route_prompt(task) -> str:
    if not task.previous_queries and not task.previous_source_families:
        return ""
    return (
        "[RETRY — CHANGE ROUTE]\n"
        "Use a different query family and different sources from the previous attempt. "
        "Exact routes with empty or permanent-failure outcomes are blocked. "
        "Different pages, windows and access methods remain available. "
        "Change the search terms, source, language, or access method. "
        "If no alternative is available, report the limitation instead of repeating the route.\n"
        "Previous queries: " + json.dumps(task.previous_queries, ensure_ascii=False) + "\n"
        "Previous source families: " + json.dumps(task.previous_source_families, ensure_ascii=False)
    )


def check_and_record_route(workspace, worker: str, tool: str, args) -> str:
    if workspace is None or not isinstance(args, dict):
        return ""
    if tool not in {
        "exec",
        "search",
        "open",
        "read_visual",
        "explore_web",

        "local_open",
        "local_find",
        "find",
    } and not tool.startswith("skill_"):
        return ""
    state = workspace.load_state()
    if not any(q.assigned_agent_id == worker for q in state.frontier.questions):
        return ""
    queries, families = call_routes(tool, args)
    if not queries and not families:
        return ""
    error = ""

    def update(state):
        nonlocal error
        task = next((q for q in state.frontier.questions if q.assigned_agent_id == worker), None)
        if task is None:
            return state
        prior_queries = {query_family(q) for q in task.previous_queries}
        repeated = [q for q in queries if query_family(q) in prior_queries]
        # Legacy hostname records cannot establish that a new page/window failed.
        # New records classify actual outcomes instead of banning all attempted queries.
        if task.route_history:
            repeated = []
        signature = route_signature(tool, args)
        repeated += [
            signature
            for record in task.route_history
            if record.get("signature") == signature
            and record.get("outcome") in {"empty", "permanent_error"}
            and record.get("worker") != worker
        ]
        if repeated:
            error = (
                "[Harness RETRY_ROUTE_BLOCKED] Previous-attempt route: "
                + ", ".join(repeated)
                + ". Change the page, window, query or access method; "
                "do not repeat this exact call."
            )
            return state
        task.attempt_queries = list(dict.fromkeys(task.attempt_queries + queries))
        task.attempt_source_families = list(dict.fromkeys(task.attempt_source_families + families))
        return state

    workspace.atomic_update_state(update)
    return error


def route_signature(tool: str, args: dict) -> str:
    """Identity includes access method and requested window, not only the host."""
    params = dict(args)
    if tool == "exec":
        from searchos.skills.names import canonical_skill_name
        params["skill"] = canonical_skill_name(str(params.get("skill", "")))
        # Command identity is package + actual arguments, independent of timeout.
        params = {key: params[key] for key in ("skill", "argv", "stdin") if key in params}
        try:
            from searchos.tools.skills.execution import _loaded
            binding = _loaded(str(params.get("skill", "")))
            params["package_hash"] = binding["package_hash"]
        except (ValueError, OSError, KeyError, RuntimeError):
            pass  # Unloaded/blocked calls can still have a stable diagnostic identity.
    if tool in {"open", "read_visual"}:
        url = params.get("id_or_url", params.get("url", ""))
        if str(url).isdigit():
            from searchos.tools.simple_browser.state import _get_browser

            browser = _get_browser()
            for key in reversed(browser.page_stack):
                page = browser.pages.get(key)
                if page is not None and str(url) in page.urls:
                    url = page.urls[str(url)]
                    break
        params.pop("id_or_url", None)
        params["url"] = url
    if tool == "find":
        from searchos.tools.simple_browser.state import _get_browser, _get_source_page

        browser = _get_browser()
        if browser.has_pages:
            params["source_url"] = _get_source_page(browser).url
    for key in ("query", "q"):
        if isinstance(params.get(key), str):
            params[key] = query_family(params[key])
    if isinstance(params.get("queries"), list):
        params["queries"] = [query_family(q) for q in params["queries"] if isinstance(q, str)]
    return json.dumps([tool, params], sort_keys=True, ensure_ascii=False, default=str)


def record_route_outcome(workspace, worker: str, signature: str, outcome: str) -> None:
    if workspace is None:
        return

    def update(state):
        task = next((q for q in state.frontier.questions if q.assigned_agent_id == worker), None)
        if task is not None:
            record = {"signature": signature, "worker": worker, "outcome": outcome}
            task.route_history = [r for r in task.route_history if r.get("signature") != signature]
            task.route_history.append(record)
        return state

    workspace.atomic_update_state(update)
