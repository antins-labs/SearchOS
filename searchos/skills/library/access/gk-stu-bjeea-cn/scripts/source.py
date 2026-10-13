"""gk_stu_bjeea_cn — 北京教育考试院站点能力集合

站点：https://gk-stu.bjeea.cn
Functions:
  - query_score_lines: 查询录取分数线（最低分/排名）
  - query_score_distribution: 查询考生分数分布统计

每个 function 是该站点下的一个独立能力。
agent 通过 skill.md 了解可用 functions，通过 `function` 参数选择调用。
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 共享基础设施
# ---------------------------------------------------------------------------

RPC_URL = "https://gk-stu.bjeea.cn/themis-student-service-api/rpc"
RPC_CLASS = "com.nazca.themis.common.rpc.student.web.StudentServiceVolunteerCoachQuerier"
RPC_HEADERS = {
    "Content-Type": "application/json",
    "Nazca-Rpc-Mode": "json",
}


async def _get_session() -> aiohttp.ClientSession:
    session = aiohttp.ClientSession()
    async with session.get("https://gk-stu.bjeea.cn/") as resp:
        await resp.read()
    await _call_rpc(session, "entryVerify", [])
    return session


async def _call_rpc(session: aiohttp.ClientSession, method: str, params: list) -> Any:
    payload = {
        "accessClass": RPC_CLASS,
        "accessMethod": method,
        "params": params,
        "deviceId": "",
    }
    async with session.post(RPC_URL, json=payload, headers=RPC_HEADERS) as resp:
        result = await resp.json(content_type=None)
    if result.get("errorCode") != 0:
        raise RuntimeError(f"RPC {method} failed: {result}")
    return result.get("returnValue")


# ---------------------------------------------------------------------------
# Function: query_score_lines
# 查询全国普通高校在京招生录取最低分和排名
# ---------------------------------------------------------------------------

async def query_score_lines(params: dict, session: aiohttp.ClientSession) -> dict:
    """查询录取分数线。

    必填：year, batch
    可选：keywords, province, page, page_size
    支持：先调用 list_years/list_batches 获取可选值
    """
    # 子操作：列出可用年份
    if params.get("list_years"):
        years_data = await _call_rpc(session, "querySystemYears", [])
        return {"years": [{"year": item["k"], "label": item["v"]["k"]} for item in years_data]}

    # 子操作：列出指定年份的批次
    if params.get("list_batches"):
        year = params.get("year", "")
        if not year:
            return {"error": "year is required for list_batches"}
        batches = await _call_rpc(session, "queryBatchs", [year])
        return {"batches": [{"code": b["code"], "name": b["name"]} for b in (batches or [])]}

    # 主操作：查询分数线
    year = params.get("year", "")
    batch = params.get("batch", "")
    if not year or not batch:
        return {"error": "year and batch are required"}

    query_params = {
        "year": year,
        "batchCode": batch,
        "provinceCodes": [params["province"]] if params.get("province") else [],
        "artExamTypeList": "",
        "electiveSubject": None,
        "byScore": None,
        "byRanking": None,
        "startScore": None,
        "endScore": None,
        "startRank": None,
        "endRank": None,
        "keywords": params.get("keywords", ""),
        "pageSize": min(params.get("page_size", 50), 50),
        "curPage": params.get("page", 1),
    }
    result = await _call_rpc(session, "queryCollegeFilingUpScoreLines", [query_params])
    if not result:
        return {"facts": [], "pagination": {"page": 1, "total_pages": 0, "total_colleges": 0}}

    facts = []
    for r in result.get("pageList", []):
        facts.append({
            "高校代码": r.get("collegeBJCode", ""),
            "高校名称": r.get("collegeName", ""),
            "省份": r.get("provinceName", ""),
            "专业组代码": r.get("majorGroupCode", ""),
            "专业组（选科要求）": r.get("majorGroupName", ""),
            "最低录取分数线": r.get("minAdmissionScoreLine"),
            "最低录取排名": r.get("minAdmissionRank"),
            "最低分专业名称": r.get("minAdmissionScoreMajorName", ""),
            "录取数分布": r.get("stuCountRanges", []),
        })

    return {
        "facts": facts,
        "pagination": {
            "page": result.get("curPage", 1),
            "total_pages": result.get("pageCount", 1),
            "total_colleges": result.get("totalCount", len(facts)),
        },
    }


# ---------------------------------------------------------------------------
# Function: query_score_distribution
# 查询高考考生分数分布（一分一段表链接）
# ---------------------------------------------------------------------------

async def query_score_distribution(params: dict, session: aiohttp.ClientSession) -> dict:
    """查询各年份考生分数分布统计表的官方链接。"""
    years_data = await _call_rpc(session, "querySystemYears", [])
    if not years_data:
        return {"distributions": []}
    distributions = [
        {"year": item["k"], "title": item["v"]["k"], "url": item["v"]["v"]}
        for item in years_data
    ]
    target_year = params.get("year", "")
    if target_year:
        distributions = [d for d in distributions if d["year"] == target_year]
    return {"distributions": distributions}


# ---------------------------------------------------------------------------
# Function Registry + Entry Point
# ---------------------------------------------------------------------------

FUNCTIONS = {
    "query_score_lines": query_score_lines,
    "query_score_distribution": query_score_distribution,
}


async def execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    fn_name = params.get("function", "")
    if not fn_name:
        return {"error": "function is required", "available_functions": list(FUNCTIONS.keys())}

    fn = FUNCTIONS.get(fn_name)
    if not fn:
        return {"error": f"Unknown function: {fn_name}", "available_functions": list(FUNCTIONS.keys())}

    session = await _get_session()
    try:
        return await fn(params, session)
    finally:
        await session.close()
