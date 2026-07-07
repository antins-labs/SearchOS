# Access Skill 目录规范

本文档定义 `skills/library/access/<skill_name>/` 下每个子目录的契约。
`AccessSkillDispatcher` 启动时扫描所有子目录，按 `manifest.yaml` 的 `tier`
字段选择不同的执行路径。

## 目录结构

```
searchos/skills/library/access/<skill_name>/
├── skill.md              # 人类可读文档（既有格式，YAML frontmatter + markdown）
├── manifest.yaml         # Dispatcher 元数据（路由、tier、字段）
├── selectors.yaml        # [T1/T2] CSS / XPath 字段映射
├── schema.py             # [T2/T3] Pydantic 输出模型
├── executor.py           # [T4] Python 执行器（既有接口，兼容保留）
└── fixtures/
    └── urls.txt          # 2-3 个代表性 URL，供 practice 和 health-check 使用
```

**只有 `skill.md` 是强制的**。其余文件按 `tier` 选择性提供：

| tier | 强制文件 |
|------|---------|
| T1   | manifest.yaml + selectors.yaml |
| T2   | manifest.yaml + selectors.yaml + schema.py |
| T3   | manifest.yaml + schema.py |
| T4   | manifest.yaml + executor.py |

## Tier 语义

| tier | 用途 | 运行时 | LLM 成本 |
|------|------|-------|---------|
| **T1** | 结构稳定、字段明确的站点 | 纯 CSS 选择器抽取 | 零 |
| **T2** | 字段 CSS 可定位但需 LLM 规范化 | CSS 抽 + judge 补 | 低 |
| **T3** | 字段结构化但位置不固定 | 站点专属 Pydantic + LLMExtractionStrategy | 中 |
| **T4** | 多步流程、登录、分页、JS 交互 | Python executor | 低-中 |

Dispatcher 未命中任何 access skill 时，回退到通用的
`EvidenceExtractionMiddleware`（记为 T0）。

## `manifest.yaml` 字段

```yaml
name: wikipedia_infobox          # 必填。应与目录名一致
tier: T1                         # 必填。T1 | T2 | T3 | T4
url_patterns:                    # 必填。fnmatch 风格，匹配整 URL 或主机名
  - "*.wikipedia.org/wiki/*"
  - "zh.wikipedia.org/wiki/*"
priority: 0                      # 可选，默认 0。冲突时越大越优先
trigger_keywords: []             # 可选，用于 skill 匹配诊断（不参与路由）
fields:                          # 可选，human-readable 字段清单
  - founded_year
  - headquarters
fallback_tier: T0                # 可选，抽取失败时的回退路径
```

## `selectors.yaml` 字段（T1/T2）

```yaml
fields:
  - name: title
    selector: "h1.firstHeading"
    type: text                   # text | attribute | html
  - name: infobox
    selector: "table.infobox tr"
    type: rows                   # 表格行 → list[dict]
    subfields:                   # rows 模式下必填
      key:   "th"
      value: "td"
```

## `schema.py` 要求（T2/T3）

```python
from pydantic import BaseModel, Field

class WikipediaInfoboxRow(BaseModel):
    key: str = Field(..., description="Field label, e.g. Founded")
    value: str = Field(..., description="Field value")
```

Pydantic 模型由 Dispatcher 直接转成 JSON Schema 喂给 crawl4ai 的
`LLMExtractionStrategy` 或本地 judge model。

## `fixtures/urls.txt` 要求

每行一个 URL，空行和 `#` 开头的行忽略。Dispatcher 的 health-check 循环按文件
顺序抓取并统计字段命中率，命中率低于 `settings.access_skill_health_min`
时该 skill 被标记 `degraded` 并暂停（仍留在目录，日志打告警）。

## 与 `EvidenceExtractionMiddleware` 的协作

1. sub-agent 调 `open` 打开页面
2. `BrowserService` 返回 `FetchResult(markdown, html, url, ...)`
3. `EvidenceExtractionMiddleware` 先调 `AccessSkillDispatcher.extract(url, html, markdown, query)`
4. 若返回非空 facts 列表 → 直接写 `coverage_map` + `evidence_graph`，记
   `access_skill_hit`，**跳过 T0 judge-LLM**
5. 否则走原 T0 流程（通用 prompt + judge model）

这样 Dispatcher 一旦接入，所有"站点专属"优化自动生效；没有任何 skill 时行为
与 Phase 2 完全一致。
