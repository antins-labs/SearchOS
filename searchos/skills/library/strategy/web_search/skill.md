---
name: web_search
description: 通用 Web 搜索——site/精确短语/排除词/时间约束/多来源
trigger: 任务需要在通用搜索引擎（Google / Bing 等）上检索公开网页
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
覆盖通用 Web 搜索引擎的标准操作符与多来源策略，把"想到关键词就敲进去"升级为"按搜索面规则构造可控查询"。

## 适用场景
- 公开事实、新闻、统计数据
- 没有明确权威站点时的初步定位
- 多来源交叉验证

## 规则（共 10 条）
1. **`site:` 限定**：当目标站点已知时强制 `site:domain.com`，将噪声压到最小。
2. **精确短语用引号**：人名、产品全名、报错信息用 `"..."` 锁定，避免分词扩散。
3. **`-` 排除词**：用 `-keyword` 排除常见误命中（同名不同领域、过期版本）。
4. **时间约束显式化**：`after:YYYY-MM-DD` / 引擎的"过去一年"过滤器，处理时效字段。
5. **`filetype:` 用于公文/报告**：`filetype:pdf` 命中监管披露、白皮书、年报。
6. **多来源覆盖**：同一事实至少检索 3 个独立来源；优先权威 + 二次源 + 一次源结合。
7. **避免长自然句**：自然语言 query 容易被改写得偏离，关键词组合更可控。
8. **结果首屏即决策**：top-10 没有命中目标就 rewrite，不要翻第 3 页。
9. **跨语种镜像查询**：英文事实查不到时镜像到原文语种再查一次，反之亦然。
10. **结果去 tracking 参数**：url 去掉 `utm_*` / `?ref=` 后再去重，避免同一页面重复占位。

## 执行流程
1. 接收 `general_query_construction` 输出的 query 集合。
2. 按规则补 `site:` / 引号 / 排除词 / 时间过滤。
3. 并行发出，收 top-k。
4. 归一化 url 后去重，按权威度 × 时效 × 相关度重排。

## 关联 skill
- `general_query_construction` — 上游
- `search_recovery_and_verification` — 失败恢复
- `official_docs_api_search` — 命中官方站点后切到此 skill
