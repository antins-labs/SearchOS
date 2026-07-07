---
name: bjeea_gaokao_admission_query
site: https://gk-stu.bjeea.cn/#/app/volunteer-coach/query
provider: 北京教育考试院 (Beijing Education Examinations Authority)
backend: Nazca RPC (single endpoint, JSON-mode header required)
---

# 北京高考录取统计查询 (BJEEA 提档分数线 / 分数分布)

This skill wraps the **录取统计查询** module at `gk-stu.bjeea.cn`, which
publishes the actual admission cutoff lines and score distributions for
**universities recruiting in Beijing** for the **2022 / 2023 / 2024** college
entrance exams (高考).

## How the site works

* SPA (Angular), all calls go to a single Nazca RPC endpoint:
  `POST https://gk-stu.bjeea.cn/themis-student-service-api/rpc`
* The request body is always
  `{accessClass, accessMethod, params, deviceId}`; the response is
  `{errorCode, returnValue}` or `{errorCode, errorMsg/returnExp}`.
* **The header `Nazca-Rpc-Mode: json` is required.** Without it the server
  encodes the response as `application/octet-stream` (binary).
* Entering the `volunteer-coach` (录取统计查询) module requires:
  1. `GET /` to seed the `api_sticky` cookie.
  2. `POST` the `entryVerify` RPC – this grants the module access on the
     server side (without it, `queryBatchs` etc. return
     `errorCode: 310 服务器会话验证失败`) and sets `JSESSIONID`.

All of the above is handled inside `_get_session()` in `executor.py`.

## Functions

### `list_years`
List queryable academic years.
**Params:** none
**Returns:**
```json
{ "ok": true,
  "years": [ {"year": "2024",
              "distribution_title": "2024年北京市高考考生分数分布",
              "distribution_url": "https://..."} ] }
```

### `list_batches`
List admission batches available for a year.
**Params:** `year` (str, required)
**Returns:** `{ok, year, batches:[{code, name, art_flag, explains, sort_order}]}`
- `art_flag == "1"` 表示艺术类批次（专业分有艺术类方向 A–G）。
- Example codes seen for 2024: `"2"` 本科提前批艺术B段, `"5"` 本科提前批普通A段,
  `"6"` 本科提前批普通B段, `"9"` 本科普通批, `"B"` 专科提前批艺术, `"D"` 专科提前批普通.

### `list_provinces`
List the provinces of the colleges that recruit in Beijing for the given year.
**Params:** `year` (str, required)
**Returns:** `{ok, year, provinces:[{code, name}]}` — codes are GB/T 2260
prefixes (e.g. `"11"` 北京, `"31"` 上海).

### `list_elective_subjects`
List elective subjects (选考科目).
**Params:** `year` (str, required)
**Returns:** `{ok, year, subjects:[{code, name, type, max_score}]}`

### `list_art_exam_types`
List the art-exam direction enum used by `query_score_lines.art_exam_types`.
**Params:** none
**Returns:** `{ok, art_exam_types:[{code, name}]}`
This list is a front-end constant (no API exposes it directly):
`A` 播音与主持类, `B` 表（导）演类, `C` 舞蹈类, `D` 音乐类,
`E` 美术与设计类, `F` 书法类, `G` 戏曲类.

### `query_score_lines`
The main query. Returns one page of college / major-group rows with their
minimum admission score, minimum admission rank, and the 8-bucket score
distribution.

**Required params**
- `year` (str), e.g. `"2024"`
- `batch_code` (str), e.g. `"9"` for 本科普通批

**Optional filters**
- `province_codes` (list[str]) — college locations; empty = all.
- `art_exam_types` (list[str]) — art directions; only meaningful when
  `batch_code` is an art batch (`art_flag == "1"`).
- `elective_subject` (str|null) — elective subject code.
- `by_score` (bool) + `start_score` / `end_score` (int) — filter on min admission score range.
- `by_ranking` (bool) + `start_rank` / `end_rank` (int) — filter on min admission rank range.
- `keywords` (str) — college name / code / major name; separator: `、` `,` `;` `；` `，`.
- `page_size` (int, default 20), `cur_page` (int, default 1).
- `full` (bool, default `false`) — when `true`, return raw API entries with
  all internal fields (importerId, scoreRange ids, etc.).

**Return shape (simplified, `full=false`)**
```json
{
  "ok": true,
  "year": "2024",
  "batch_code": "9",
  "cur_page": 1,
  "page_count": 12,
  "page_size": 20,
  "total": 240,
  "items": [
    {
      "college_code": "1021",
      "college_name": "北京大学",
      "province_code": "11",
      "province_name": "北京",
      "batch_code": "9",
      "major_group_code": "04",
      "major_group_name": "不限",
      "min_admission_score": 675,
      "min_admission_rank": 1077,
      "min_admission_major_code": "47",
      "min_admission_major_name": "波斯语",
      "score_bucket_upper_bounds": [659,669,679,689,699,709,719,720],
      "majors": [
        {
          "major_code": "40",
          "major_name": "法语",
          "major_memo": null,
          "plan_count": 2,
          "art_exam_type": null,
          "art_exam_type_name": null,
          "score_bucket_counts": [0,0,0,2,0,0,0,0]
        }
      ]
    }
  ]
}
```

* `score_bucket_upper_bounds[i]` is the upper bound of bucket *i* (8 buckets
  total). For example `[659,669,679,689,699,709,719,720]` means buckets
  `<660`, `660–669`, …, `710–719`, `≥720`.
* `majors[*].score_bucket_counts` aligns with those same upper bounds and
  gives the number of admitted students in each bucket for that single
  major.

**Error shape**
```json
{ "ok": false, "error_code": 310, "error_msg": "服务器会话验证失败！" }
```
The executor builds a fresh session for every call, so 310 should be rare;
if you see it, just retry.

## Example agent workflows

1. **"北京大学 2024 在京招生分数线"**
   ```
   query_score_lines(year="2024", batch_code="9", keywords="北京大学")
   ```
   (Use `list_batches(year="2024")` first if you are unsure which batch.)

2. **"2024 年本科提前批艺术 B 段，音乐类，按分数 580 以上的院校"**
   ```
   query_score_lines(
     year="2024", batch_code="2",
     art_exam_types=["D"],
     by_score=True, start_score=580, end_score=750,
   )
   ```

3. **"上海地区高校 2023 年本科普通批，分数 600–650 段"**
   ```
   query_score_lines(
     year="2023", batch_code="9",
     province_codes=["31"],
     by_score=True, start_score=600, end_score=650,
   )
   ```
