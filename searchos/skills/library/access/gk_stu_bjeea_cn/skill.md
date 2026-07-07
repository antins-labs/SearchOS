---
name: gk_stu_bjeea_cn
layer: access
invocation: agent_called
status: active
---

# gk_stu_bjeea_cn

北京教育考试院（gk-stu.bjeea.cn）站点能力集合。

## Functions

### query_score_lines

查询全国普通高校在京招生录取最低分和排名。

**参数：**
- `year`（必填）— 年份
- `batch`（必填）— 批次代码
- `keywords` — 高校名称/代码关键词
- `province` — 省份代码
- `page` / `page_size` — 分页

**辅助子操作：**
- `list_years: true` — 返回可用年份列表
- `list_batches: true` + `year` — 返回该年份的批次列表

**返回字段：** 高校代码、高校名称、省份、专业组（选科要求）、最低录取分数线、最低录取排名、最低分专业名称、录取数分布

**典型调用流程：**
1. `{function: "query_score_lines", list_years: true}` → 获取可用年份
2. `{function: "query_score_lines", list_batches: true, year: "2024"}` → 获取批次
3. `{function: "query_score_lines", year: "2024", batch: "9"}` → 查询本科普通批分数线

---

### query_score_distribution

查询各年份考生分数分布统计表（一分一段表）的官方链接。

**参数：**
- `year`（可选）— 指定年份，不填返回所有年份

**返回：** `{distributions: [{year, title, url}]}`

---

## 批次代码参考

| 代码 | 名称 |
|------|------|
| 2 | 本科提前批艺术B段 |
| 5 | 本科提前批普通A段 |
| 6 | 本科提前批普通B段 |
| 9 | 本科普通批 |
| B | 专科提前批艺术 |
| D | 专科提前批普通 |
| E | 专科普通批 |

## 技术要点

- RPC 接口 + `Nazca-Rpc-Mode: json` header
- 需 session 初始化（GET 首页 + entryVerify）
- 依赖 `aiohttp`
