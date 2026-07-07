---
name: general_query_construction
description: 通用查询构造——拆解用户意图，保留关键实体，生成精确与召回查询
trigger: 任何检索任务的起点；在选择具体搜索面（web / github / 论坛 / 文档 / 学术）之前，先按本 skill 构造查询
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
为下游所有搜索面提供统一的查询构造方法：先把用户意图拆成可检索的子事实，再为每个子事实同时生成精确（precision）与召回（recall）两类查询。

## 适用场景
- 任何检索任务的预处理阶段
- 单条 query 难以覆盖问句中多个事实点

## 规则（共 12 条）
1. **拆解意图**：先把问句拆成 who / what / when / where / value / relation 子事实，每个子事实独立成 query 单元。
2. **保留关键实体的规范名**：人名、机构名、产品名要使用规范化形式（含官方拼写、缩写、别名集合）。
3. **关键实体不被改写**：query rewrite 阶段允许改谓词与修饰词，但实体保持原样。
4. **同时生成 precision 与 recall 两类**：精确查询用规范名 + 关键属性词；召回查询用上位词 / 同义词 / 模糊描述。
5. **每个子事实至少 2 条 query**：1 条 precision，1 条 recall，缺失要标记原因。
6. **限定词与实体分离**：时间、地点、版本等限定条件作为可拆装的修饰段，便于在迭代中增删。
7. **禁止过长 query**：单条 query 关键词数量控制在 2–6 个之间，过长会被搜索引擎降权。
8. **多语种并行**：跨语种实体（中英、日中等）至少各生成一条对应语种的 query。
9. **禁用一次性长尾问句**：把"X 在 Y 条件下的 Z 是多少"这种自然句改写成关键词组合，不要直接搜整句。
10. **每条 query 写明 expected signal**：发出前注明"我期望它命中什么"，用于失败诊断。
11. **去重在结果层**：允许 query 之间重叠，去重交给结果归一化阶段。
12. **当首批 query 全部失败**：触发 rewrite 而非简单加 query；rewrite 时换术语 / 换语种 / 换问法。

## 执行流程
1. 拆问句为子事实清单。
2. 对每个子事实生成 precision + recall query 对。
3. 标注限定词（时间、地点、版本）。
4. 多语种镜像。
5. 输出 query 集合，交给具体搜索面。

## 关联 skill
- 各搜索面 skill（`web_search`、`github_search`、`codebase_search`、`forum_search`、`official_docs_api_search`、`academic_literature_search`）
- `search_recovery_and_verification` — 失败时的统一恢复入口
