"""
SearchOS access skill: 北京教育考试院 - 高考录取统计查询
站点: https://gk-stu.bjeea.cn/#/app/volunteer-coach/query

后端是 Java/Nazca RPC, 单一端点 POST /themis-student-service-api/rpc。
所有调用结构: {accessClass, accessMethod, params, deviceId}.
必须带 header `Nazca-Rpc-Mode: json`，否则服务器返回二进制（octet-stream）格式。
进入查询模块前需要先 GET 首页拿 cookie，再调用 entryVerify 建立会话。
"""

from __future__ import annotations

import json
from typing import Any

import aiohttp

# ------------------------ Constants ------------------------

BASE = "https://gk-stu.bjeea.cn"
HOME_URL = f"{BASE}/"
RPC_URL = f"{BASE}/themis-student-service-api/rpc"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

RPC_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": BASE,
    "Referer": f"{BASE}/",
    "Nazca-Rpc-Mode": "json",  # <-- 关键 header
}

VOL_COACH = "com.nazca.themis.common.rpc.student.web.StudentServiceVolunteerCoachQuerier"
COMMON = "com.nazca.themis.common.rpc.student.web.StudentServiceCommonQuerier"

# 前端固定的艺术类方向枚举（非 API 返回，从响应数据观察）
ART_EXAM_TYPES = [
    {"code": "A", "name": "播音与主持类"},
    {"code": "B", "name": "表（导）演类"},
    {"code": "C", "name": "舞蹈类"},
    {"code": "D", "name": "音乐类"},
    {"code": "E", "name": "美术与设计类"},
    {"code": "F", "name": "书法类"},
    {"code": "G", "name": "戏曲类"},
]


# ------------------------ Session / RPC plumbing ------------------------

async def _get_session() -> aiohttp.ClientSession:
    """Create a session, hit the homepage to seed cookies, and run entryVerify."""
    session = aiohttp.ClientSession()
    # 1) Hit homepage to get api_sticky cookie
    async with session.get(HOME_URL, headers={"User-Agent": USER_AGENT}) as r:
        await r.read()
    # 2) entryVerify – grants access to volunteer-coach module (also sets JSESSIONID)
    await _rpc(session, VOL_COACH, "entryVerify", [])
    return session


async def _rpc(
    session: aiohttp.ClientSession,
    access_class: str,
    access_method: str,
    params: list[Any],
) -> dict[str, Any]:
    """Make one Nazca RPC call and return parsed JSON."""
    payload = {
        "accessClass": access_class,
        "accessMethod": access_method,
        "params": params,
        "deviceId": "",
    }
    async with session.post(
        RPC_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=RPC_HEADERS,
    ) as r:
        text = await r.text()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"errorCode": -1, "errorMsg": f"Non-JSON response: {text[:300]}"}


def _unwrap(resp: dict[str, Any]) -> dict[str, Any]:
    """Convert RPC envelope into a friendlier {ok, data | error} shape."""
    code = resp.get("errorCode")
    if code == 0:
        return {"ok": True, "data": resp.get("returnValue")}
    msg = resp.get("errorMsg")
    if not msg and isinstance(resp.get("returnExp"), dict):
        msg = resp["returnExp"].get("localizedMessage") or resp["returnExp"].get("message")
    return {"ok": False, "error_code": code, "error_msg": msg or "unknown error"}


# ------------------------ Public functions ------------------------

async def list_years(params: dict, session: aiohttp.ClientSession) -> dict:
    """List queryable academic years for the recruitment statistics query."""
    r = _unwrap(await _rpc(session, VOL_COACH, "querySystemYears", []))
    if not r["ok"]:
        return r
    # data is a list of {k: year, v: {k: title, v: url}}
    years = []
    for item in r["data"] or []:
        years.append({
            "year": item.get("k"),
            "distribution_title": (item.get("v") or {}).get("k"),
            "distribution_url": (item.get("v") or {}).get("v"),
        })
    return {"ok": True, "years": years}


async def list_batches(params: dict, session: aiohttp.ClientSession) -> dict:
    """List admission batches for a given year. params: {year: "2024"}."""
    year = str(params.get("year", "")).strip()
    if not year:
        return {"ok": False, "error_msg": "year is required (e.g. '2024')"}
    r = _unwrap(await _rpc(session, VOL_COACH, "queryBatchs", [year]))
    if not r["ok"]:
        return r
    batches = []
    for b in r["data"] or []:
        batches.append({
            "code": b.get("code"),
            "name": b.get("name"),
            "art_flag": b.get("artFlag"),  # "1" if 艺术类
            "explains": b.get("explains"),
            "sort_order": b.get("sortOrder"),
        })
    return {"ok": True, "year": year, "batches": batches}


async def list_provinces(params: dict, session: aiohttp.ClientSession) -> dict:
    """List recruiting college provinces for a year. params: {year: "2024"}."""
    year = str(params.get("year", "")).strip()
    if not year:
        return {"ok": False, "error_msg": "year is required"}
    r = _unwrap(await _rpc(session, VOL_COACH, "queryRecruitCollegeProvinces", [year]))
    if not r["ok"]:
        return r
    provinces = [{"code": p.get("code"), "name": p.get("name")} for p in (r["data"] or [])]
    return {"ok": True, "year": year, "provinces": provinces}


async def list_elective_subjects(params: dict, session: aiohttp.ClientSession) -> dict:
    """List elective subjects (选考科目) for a year. params: {year: "2024"}."""
    year = str(params.get("year", "")).strip()
    if not year:
        return {"ok": False, "error_msg": "year is required"}
    r = _unwrap(await _rpc(session, VOL_COACH, "queryElectiveSubjects", [year]))
    if not r["ok"]:
        return r
    subjects = []
    for s in r["data"] or []:
        subjects.append({
            "code": s.get("code"),
            "name": s.get("name"),
            "type": s.get("type"),
            "max_score": s.get("maxScore"),
        })
    return {"ok": True, "year": year, "subjects": subjects}


async def list_art_exam_types(params: dict, session: aiohttp.ClientSession) -> dict:
    """List art-exam direction options (front-end constants, used to filter art batches)."""
    return {"ok": True, "art_exam_types": ART_EXAM_TYPES}


async def query_score_lines(params: dict, session: aiohttp.ClientSession) -> dict:
    """
    Main query: college admission cutoff lines & score distributions.

    Required params:
      year (str)        – e.g. "2024" (must be among list_years output: 2022/2023/2024)
      batch_code (str)  – e.g. "2" (from list_batches; "2" 本科提前批艺术B段)

    Optional filters:
      province_codes (list[str])   – college locations, e.g. ["11","31"]; empty = all
      art_exam_types (list[str])   – e.g. ["A","C"]; only meaningful for art batches
      elective_subject (str|null)  – elective subject code (from list_elective_subjects)
      by_score (bool)              – filter by score range
      by_ranking (bool)            – filter by ranking range
      start_score / end_score (int)
      start_rank  / end_rank (int)
      keywords (str)               – college name / code / major name; separator: 、, ;
      page_size (int, default 20)
      cur_page (int, default 1)
      full (bool, default False)   – if True, return raw API entries; else simplified
    """
    year = str(params.get("year", "")).strip()
    batch_code = str(params.get("batch_code", "")).strip()
    if not year or not batch_code:
        return {"ok": False, "error_msg": "year and batch_code are required"}

    province_codes = params.get("province_codes") or []
    if isinstance(province_codes, str):
        province_codes = [p.strip() for p in province_codes.split(",") if p.strip()]

    art_types = params.get("art_exam_types") or ""
    if isinstance(art_types, list):
        # API expects a comma-joined string like "A,C"
        art_types = ",".join(art_types)

    page_size = int(params.get("page_size") or 20)
    cur_page = int(params.get("cur_page") or 1)

    api_params = [{
        "year": year,
        "batchCode": batch_code,
        "provinceCodes": list(province_codes),
        "artExamTypeList": art_types,
        "electiveSubject": params.get("elective_subject"),
        "byScore": params.get("by_score"),
        "byRanking": params.get("by_ranking"),
        "startScore": params.get("start_score"),
        "endScore": params.get("end_score"),
        "startRank": params.get("start_rank"),
        "endRank": params.get("end_rank"),
        "keywords": params.get("keywords") or "",
        "pageSize": page_size,
        "curPage": cur_page,
    }]
    r = _unwrap(await _rpc(session, VOL_COACH, "queryCollegeFilingUpScoreLines", api_params))
    if not r["ok"]:
        return r

    data = r["data"] or {}
    page_list = data.get("pageList") or []
    full = bool(params.get("full"))

    if full:
        items = page_list
    else:
        items = [_simplify_score_entry(e) for e in page_list]

    return {
        "ok": True,
        "year": year,
        "batch_code": batch_code,
        "cur_page": data.get("curPage"),
        "page_count": data.get("pageCount"),
        "page_size": page_size,
        "total": data.get("totalCount") or data.get("rowCount"),
        "items": items,
    }


def _simplify_score_entry(e: dict) -> dict:
    """Reduce one college entry to the most useful columns."""
    sr = e.get("scoreRange") or {}
    score_buckets = None
    if sr:
        # endScore1..endScore8: upper bound of each score bucket (used by 分数分布)
        score_buckets = [sr.get(f"endScore{i}") for i in range(1, 9)]

    majors = []
    for m in e.get("stuCountRanges") or []:
        counts = [m.get(f"admissionCount{i}") for i in range(1, 9)]
        majors.append({
            "major_code": m.get("majorCode"),
            "major_name": m.get("majorName"),
            "major_memo": m.get("majorMemo"),
            "plan_count": m.get("planCount"),
            "art_exam_type": m.get("artExamType"),
            "art_exam_type_name": m.get("artExamTypeName"),
            "score_bucket_counts": counts,
        })

    return {
        "college_code": e.get("collegeBJCode"),
        "college_name": e.get("collegeName"),
        "province_code": e.get("provinceCode"),
        "province_name": e.get("provinceName"),
        "batch_code": e.get("batchCode"),
        "major_group_code": e.get("majorGroupCode"),
        "major_group_name": e.get("majorGroupName"),
        "min_admission_score": e.get("minAdmissionScoreLine"),
        "min_admission_rank": e.get("minAdmissionRank"),
        "min_admission_major_code": e.get("minAdmissionScoreMajorCode"),
        "min_admission_major_name": e.get("minAdmissionScoreMajorName"),
        "score_bucket_upper_bounds": score_buckets,
        "majors": majors,
    }


# ------------------------ Registry / entrypoint ------------------------

FUNCTIONS = {
    "list_years": list_years,
    "list_batches": list_batches,
    "list_provinces": list_provinces,
    "list_elective_subjects": list_elective_subjects,
    "list_art_exam_types": list_art_exam_types,
    "query_score_lines": query_score_lines,
}


async def execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    fn_name = params.get("function", "")
    if not fn_name:
        return {
            "error": "function is required",
            "available_functions": list(FUNCTIONS.keys()),
        }
    fn = FUNCTIONS.get(fn_name)
    if not fn:
        return {
            "error": f"Unknown function: {fn_name}",
            "available_functions": list(FUNCTIONS.keys()),
        }
    session = await _get_session()
    try:
        return await fn(params, session)
    finally:
        await session.close()
