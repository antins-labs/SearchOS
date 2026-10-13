---
name: guard-skill-academic-paper
description: 'Guard against skill anti-pattern: academic_paper'
metadata:
  searchos-category: strategy
  searchos-aliases: guard_skill_academic_paper
  searchos-config: '{"name": "guard_skill_academic_paper", "description": "Guard against
    skill anti-pattern: academic_paper", "category": "strategy", "trigger": "avoid
    skill signature ''academic_paper''", "availability": "enabled", "has_executor":
    false, "compatibility": "", "metadata": {}}'
compatibility: 方法型技能；使用当前宿主已有的搜索、阅读和记录能力。
---

# 使用边界

下文给出研究方法。提到 schema、任务派发或证据工具时，仅在宿主提供对应能力时调用；其他环境用表格、任务清单和附来源的笔记表达相同状态，不假定专有工具存在。具体方法和约束如下。

# Guard skill (mined from session anti-pattern)

**Kind**: `skill`  
**Signature**: `academic-paper`  
**Observed**: 3× 
**Reason**: access-skill executor returned no new evidence  

## Avoid
When the current task matches this signature, don't repeat this path. Prior sessions proved it unproductive (3 hits).
