"""工具调用的资源计量函数。"""

from typing import Any


def tool_costs(name: str, args: Any) -> dict[str, int]:
    costs = {}
    if name in {
        "web_search",
        "tavily_search",
        "serper_search",
        "browser_navigate",
        "search",
        "explore_web",
        "local_catalog",
    }:
        costs["search"] = 1
    if name in {"open", "read_visual", "browser_open", "explore_web", "local_open"}:
        costs["open"] = 1
    if name in {"find", "browser_find", "local_find"}:
        costs["find"] = 1
    if name == "exec" or name.startswith("skill_"):
        costs["skill"] = 1
    if name == "explore_web" and isinstance(args, dict):
        queries = args.get("queries") or []
        count = max(1, len(queries) if isinstance(queries, (list, tuple)) else 1)
        try:
            top_k = max(1, min(int(args.get("open_top_k", 1)), 2))
        except (TypeError, ValueError):
            top_k = 1
        costs.update(search=count, open=count * top_k)
    return costs
