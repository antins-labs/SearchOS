import type { CoverageCell, ModelDistributionItem, RepairCellTarget, SearchState, TokenPhaseUsage, TokenUsage, WSEvent } from "./types";
import type { WorkerInfo } from "@/hooks/useSearch";

export interface RepairCellSnapshot extends RepairCellTarget {
  before: Pick<CoverageCell, "status" | "value">;
}

export interface Turn {
  id: string;
  query: string;
  sessionId: string | null;
  status: "running" | "completed" | "error";
  events: WSEvent[];
  workers: WorkerInfo[];
  searchState: SearchState | null;
  stateSource?: "live" | "snapshot" | "latest" | "unavailable";
  answer: string;
  /** Live follow-ups steered into this turn while it was running. */
  followUps?: string[];
  /** Scope and baseline retained for a targeted coverage repair turn. */
  repair?: {
    cells: RepairCellSnapshot[];
    evidenceIdsBefore: string[];
    planner?: "llm" | "deterministic";
    planningLatencyMs?: number;
    planningWarning?: string | null;
  };
  meta: {
    coverageScore?: number;
    evidenceCount?: number;
    elapsed?: number;
    verdict?: string | null;
    totalQueries?: number;
    totalSteps?: number;
    toolCounts?: Record<string, number>;
    tokenUsage?: TokenUsage;
    tokenPhases?: Record<string, TokenPhaseUsage>;
    modelDistribution?: Record<string, ModelDistributionItem>;
  };
  error?: string | null;
}
