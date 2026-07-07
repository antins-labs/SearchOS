---
name: official_docs_api_search
description: 官方文档与 API 搜索——优先文档、变更日志、迁移指南、参数说明
trigger: 任务涉及某库 / 服务 / 平台的 API 行为、参数语义、版本差异、迁移路径
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
事实层问题（参数语义、行为、版本差异）必须以官方文档为 ground truth。本 skill 强制把"能看官方就不要看二手"作为第一原则。

## 适用场景
- 参数 / 返回值 / 默认值 / 副作用查询
- 版本差异 / breaking change
- 迁移路径 / 升级指南

## 规则（共 8 条）
1. **官方 doc 优先级最高**：vendor 主站 doc > GitHub README > 官方 blog > 任何二手内容。
2. **明确目标版本**：query 必须带版本号；缺失会读到不适用的旧/新文档。
3. **变更日志专项检索**：行为差异 / 弃用 / 默认值变化必须查 CHANGELOG / Release Notes。
4. **迁移指南专项**：跨大版本时找 "migration guide" / "upgrade guide" / "breaking changes"。
5. **API reference 专项**：参数语义 / 返回值 / 错误码用 reference 章节，不要从教程类页面推断。
6. **doc 与源码不一致时以源码为准**：但需在答案中显式标注差异。
7. **`site:` 限定到官方域**：通用搜索时强制 `site:docs.<vendor>.com`。
8. **搜不到时回到源码**：官方 doc 缺漏的字段，回到 GitHub 仓库的源码 / 注释 / 测试。

## 执行流程
1. 识别 vendor + 版本号。
2. `site:docs.<vendor>.com <keyword>` 锁定 reference / changelog / migration。
3. 命中 reference → 抽参数 / 默认值 / 错误码。
4. 命中 changelog → 抽版本差异。
5. 文档无答案 → 回 GitHub 源码。

## 关联 skill
- `forum_search` — 社区指向后回到本 skill 验证
- `github_search` / `codebase_search` — 文档缺漏时回到源码
- `general_query_construction` — query 构造上游
