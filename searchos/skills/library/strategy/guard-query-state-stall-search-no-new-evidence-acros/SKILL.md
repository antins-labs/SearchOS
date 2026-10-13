---
name: guard-query-state-stall-search-no-new-evidence-acros
description: 'Guard against query anti-pattern: state-stall:search no new evidence
  across 6 steps '
metadata:
  searchos-category: strategy
  searchos-aliases: guard_query_state_stall_search_no_new_evidence_acros
  searchos-config: '{"name": "guard_query_state_stall_search_no_new_evidence_acros",
    "description": "Guard against query anti-pattern: state-stall:search no new evidence
    across 6 steps ", "category": "strategy", "trigger": "avoid query signature ''state-stall:search
    no new evidence across 6 steps ''", "availability": "enabled", "has_executor":
    false, "compatibility": "", "metadata": {}}'
compatibility: 方法型技能；使用当前宿主已有的搜索、阅读和记录能力。
---

# 使用边界

下文给出研究方法。提到 schema、任务派发或证据工具时，仅在宿主提供对应能力时调用；其他环境用表格、任务清单和附来源的笔记表达相同状态，不假定专有工具存在。具体方法和约束如下。

# Guard skill (mined from session anti-pattern)

**Kind**: `query`  
**Signature**: `state-stall:search no new evidence across 6 steps `  
**Observed**: 6× 
**Reason**: repeated query with no new evidence (agent search_agent_10)  

## Avoid
When the current task matches this signature, don't repeat this path. Prior sessions proved it unproductive (6 hits).
