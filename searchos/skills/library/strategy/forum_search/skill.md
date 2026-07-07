---
name: forum_search
description: 论坛 / 社交平台搜索——经验、常见问题、失败模式与非正式解
trigger: 检索目标偏经验性、踩坑记录、变通方案；或在通用搜索中命中 Reddit / HN / Stack Overflow / 各类官方 community
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
社区平台对"是否常见、有什么坑、有哪些非官方解法"非常有价值，但不能作为事实层 ground truth。本 skill 给出社区证据的提取方法与可信度评估规则。

## 适用场景
- 找经验建议、踩坑、变通方案
- 评估某方案的常见失败模式
- 与官方文档冲突的实际行为

## 规则（共 9 条）
1. **社区是信号源，不是事实源**：版本号、API 行为、参数语义以官方为准；社区仅指向"哪里去查官方"。
2. **采纳前必须官方源验证**：社区给出的命令、配置、参数必须在官方 doc / changelog / 源码里复读。
3. **看时间戳**：超过 2 年的高赞答案默认存疑，找最近版本的对应说明。
4. **看 edited / 更新评论**：Stack Overflow 的 edited、HN / Reddit 的 OP edit、SO 的 better answer，常推翻原答案。
5. **官方 community 权重高于第三方论坛**：GitHub Discussions / OpenAI Community / AWS re:Post 等更接近官方口径。
6. **多平台一致才采信经验结论**：单一平台的"大家都说 X" 容易回声室；至少 2 个独立社区一致。
7. **失败案例特别有用**："试了 X 不行，改用 Y" 类帖子是定位官方文档盲区的高价值信号。
8. **代码片段必须复读**：社区贴的代码 / 配置必须自己跑或对照官方 doc 复读。
9. **平台搜索用站内搜索 + Google `site:`**：站内 ranking 与时间过滤更准；Google `site:` 用于跨主题召回。

## 执行流程
1. 命中社区结果 → 标记为 `signal` 而非 `evidence`。
2. 抽取关键词 / 候选答案 / 反例。
3. 用关键词回官方源做事实验证。
4. 验证通过才入答案；引用官方源，社区源作为补充链接。

## 关联 skill
- `official_docs_api_search` — 验证阶段必经
- `general_query_construction` — 关键词回流到通用 query 构造
- `search_recovery_and_verification` — 冲突与不一致处理
