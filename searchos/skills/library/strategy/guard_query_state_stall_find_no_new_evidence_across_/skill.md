---
name: guard_query_state_stall_find_no_new_evidence_across_
description: "Guard against query anti-pattern: state-stall:find no new evidence across 6 steps "
layer: strategy
trigger: avoid query signature 'state-stall:find no new evidence across 6 steps '
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
**Signature**: `state-stall:find no new evidence across 6 steps `  
**Observed**: 3× 
**Reason**: repeated query with no new evidence (agent explore_agent_1)  

## Avoid
When the current task matches this signature, don't repeat this path. Prior sessions proved it unproductive (3 hits).