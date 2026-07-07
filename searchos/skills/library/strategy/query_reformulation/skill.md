---
name: query_reformulation
description: 通用查询词构造策略：避免Golden Document Fallacy，使用Exploration-Coverage-Synthesis范式构造高质量搜索词
trigger: 所有需要网络搜索的任务
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - any
  attribute_types:
  - any
  coverage_gap_pattern: zero_result_query
cost_hint: low
effectiveness_score: 0.0
---

# Skill: Query Reformulation（查询词构造与优化策略）

## 目标
解决 LLM search agent 在构造搜索查询词时的系统性缺陷：
1. **避免 Golden Document Fallacy**：LLM 倾向于假设存在一个"黄金文档"能直接回答原始问题，因此生成过长、过细的查询词试图一步到位
2. **建立 Exploration → Coverage → Verification 的渐进式查询策略**：从宽泛探测逐步收窄到精确提取
3. **提供查询失败后的角度切换指南**：避免同义重复搜索

核心策略：**先探测 → 再聚焦 → 后验证**。每次搜索前先自检查询质量。

## 适用场景
所有需要网络搜索的任务。本 skill 与领域型 skill（data_spec_retrieval, ranking_top_n 等）正交——领域 skill 解决"去哪找"，本 skill 解决"怎么搜"。

## 不适用场景
- 无需搜索的纯分析/计算任务
- 已知精确 URL 可直接访问的任务

## 核心原则

### 原则1：查询词 ≠ 原始问题
搜索引擎是关键词匹配系统，不是问答系统。绝不将原始问题直接或近似复制为查询词。
必须从原始问题中**提取**最具区分度的 1-2 个核心实体作为搜索起点。

### 原则2：渐进式查询（E-C-S 范式）
遵循 Exploration → Coverage → Synthesis 三阶段：
- **Exploration**：用最少关键词探测信息分布和权威源位置
- **Coverage**：基于探测结果，按信息维度逐个补充缺失字段
- **Verification**：针对冲突或低信度数据的定向验证
- **特别说明（聚合任务）**：对于需要"列举所有/主要"的聚合型任务（如"梳理所有X的情况"），Exploration 阶段的目标不是直接获取答案，而是枚举关键实体列表。随后进入 Coverage 阶段，针对每个实体发起并行查询。切忌试图用单一查询词获取全景信息（即 Decomposition-for-Aggregation 策略）。

### 原则3：失败后换角度，不换措辞
如果一次搜索没有返回有用结果，问题不在于"我的关键词不够准确"，而是"我的搜索角度不对"。
换角度的方式：换源（site:）、换语言、换信息维度、换实体粒度。

### 原则4：查询语言匹配内容语言
搜索中文内容用中文查询，搜索英文内容用英文查询。不要用英文搜中文数据，反之亦然。

