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
    planner?: "orchestrator" | "llm" | "deterministic";
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

/** Align durable trajectory segments with completed dialogue turns.
 * Interrupted task_start segments have no task_complete and are excluded so
 * they cannot shift an earlier version's Agent/tool trace. */
export function historyEventSegments(events: WSEvent[], turnCount: number): WSEvent[][] {
  if (turnCount <= 0) return [];
  const segments: WSEvent[][] = [];
  for (const event of events) {
    const data = (event.data ?? {}) as Record<string, unknown>;
    const boundary = event.type === "trajectory" && data.type === "task_start";
    if (boundary || segments.length === 0) segments.push([]);
    segments[segments.length - 1].push(event);
  }
  const completed = segments.filter((segment) => segment.some((event) => (
    event.type === "trajectory"
    && (event.data as Record<string, unknown> | undefined)?.type === "task_complete"
  )));
  const candidates = completed.length > 0 ? completed : segments;
  const aligned = candidates.slice(-turnCount);
  const leadingEmpty = Math.max(0, turnCount - aligned.length);
  return Array.from(
    { length: turnCount },
    (_, index) => aligned[index - leadingEmpty] ?? [],
  );
}
