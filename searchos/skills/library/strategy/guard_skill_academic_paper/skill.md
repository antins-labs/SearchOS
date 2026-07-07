---
name: guard_skill_academic_paper
description: "Guard against skill anti-pattern: academic_paper"
layer: strategy
trigger: avoid skill signature 'academic_paper'
trigger_conditions:
  domain: ['general']
  entity_types: [any]
  attribute_types: [any]
  coverage_gap_pattern: anti_pattern_skill
cost_hint: low
status: seed
success_rate: 0.0
---
# Guard skill (mined from session anti-pattern)

**Kind**: `skill`  
**Signature**: `academic_paper`  
**Observed**: 3× 
**Reason**: access-skill executor returned no new evidence  

## Avoid
When the current task matches this signature, don't repeat this path. Prior sessions proved it unproductive (3 hits).