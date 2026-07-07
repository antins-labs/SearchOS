---
name: guard_query_state_stall_search_no_new_evidence_acros
description: "Guard against query anti-pattern: state-stall:search no new evidence across 6 steps "
layer: strategy
trigger: avoid query signature 'state-stall:search no new evidence across 6 steps '
trigger_conditions:
  domain: ['general']
  entity_types: [any]
  attribute_types: [any]
  coverage_gap_pattern: anti_pattern_query
cost_hint: low
status: seed
success_rate: 0.0
---
# Guard skill (mined from session anti-pattern)

**Kind**: `query`  
**Signature**: `state-stall:search no new evidence across 6 steps `  
**Observed**: 6× 
**Reason**: repeated query with no new evidence (agent search_agent_10)  

## Avoid
When the current task matches this signature, don't repeat this path. Prior sessions proved it unproductive (6 hits).