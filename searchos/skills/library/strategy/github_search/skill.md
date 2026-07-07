---
name: github_search
description: GitHub 搜索——仓库 / Issue / PR / 符号 / 变更历史
trigger: 任务涉及在 GitHub 上检索代码、议题、合并请求、版本历史或符号定义
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
GitHub 内的搜索语义与通用 Web 搜索差别很大，必须切换到 GitHub Code Search 限定符。本 skill 给出仓库、Issue、PR、符号、变更历史五个面向的检索规则。

## 适用场景
- 找用法 / 找历史决策 / 找版本变更 / 找符号定义

## 规则（共 13 条）
1. **`repo:` / `org:` 限定**：跨仓库搜索时必带，否则结果近似随机。
2. **`language:`**：明确语言后召回率显著提升。
3. **`path:`**：用 `path:**/tests/**` / `path:docs/**` 收紧位置。
4. **`symbol:`**：找符号定义优先 `symbol:Foo`，比正则匹配更准确。
5. **`extension:` / `filename:`**：定位 Dockerfile / Makefile / `*.toml` 等约定文件。
6. **Issue 用 `is:issue` + `state:`**：`is:issue is:closed reason:completed` 找已解决问题。
7. **PR 用 `is:pr is:merged`**：未合并的 PR 不能作为最终方案。
8. **结论看 merged commit message + 末段评论**：楼主原帖常常不是结论。
9. **变更历史用 `repo:.../commits` 检索**：搜 commit message 里的关键词比搜代码更直达"什么时候改的"。
10. **`label:`**：项目自定义 label（bug / regression / breaking-change）是高信号过滤器。
11. **跨仓库结果按维护活跃度排序**：stars + 最近 commit + open/closed issue 比例，避免选到弃坑仓库。
12. **`in:title` / `in:body`**：搜 issue 时区分标题与正文，标题命中权重更高。
13. **优先 official org**：同名仓库存在时（fork / mirror），优先官方组织名下的版本作为 ground truth。

## 执行流程
1. 判断目标面：repo / issue / pr / symbol / commits。
2. 套用对应限定符模板。
3. 结果按活跃度 + 官方度排序。
4. 进入仓库后，结合 `codebase_search` 做精确定位。

## 关联 skill
- `codebase_search` — 进入仓库后的精确 / 结构搜索
- `forum_search` — 议题里的社区讨论用社区规则评估
- `general_query_construction` — query 构造上游
