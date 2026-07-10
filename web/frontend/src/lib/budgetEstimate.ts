import type { EffortLevel } from "./types";

export interface BudgetEstimate {
  level: EffortLevel;
  maxTimeSeconds: number;
  parallelAgents: number;
  searchesPerAgent: number;
  searchesPerWave: number;
}

export function estimateRunBudget(
  level: EffortLevel,
  levels: Record<EffortLevel, Record<string, number>>,
  maxTimeOverride?: number,
): BudgetEstimate {
  const knobs = levels[level] ?? {};
  const parallelAgents = Math.max(1, knobs.max_parallel_agents ?? 1);
  const searchesPerAgent = Math.max(0, knobs.max_searches_per_sub_agent ?? 0);
  return {
    level,
    maxTimeSeconds: maxTimeOverride ?? knobs.default_max_time_s ?? 0,
    parallelAgents,
    searchesPerAgent,
    searchesPerWave: parallelAgents * searchesPerAgent,
  };
}
