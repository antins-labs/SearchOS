import type { CoverageCell, ModelDistributionItem, RepairCellTarget, SearchState, TokenPhaseUsage, TokenUsage, WSEvent } from "./types";
import type { WorkerInfo } from "./types";

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
  sourceMode?: "web" | "local" | "hybrid";
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
    startedAt?: number;
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

/** Missing terminal output is an interrupted run, not a completed answer. */
export function restoredRunState(status: "running" | "completed" | "incomplete" | "error"):
  { status: Turn["status"]; error: string | null } {
  if (status === "incomplete") return {
    status: "error",
    error: "这次运行已中断，尚未生成最终回答。下方保留的是中间输出和运行记录，可重新运行该问题。",
  };
  return { status, error: status === "error" ? "这次运行失败，请查看运行记录。" : null };
}

/** Continue only the immediately preceding, completed conversation of the
 * conversation. The server resets evidence when the submitted source scope
 * changes, while preserving the conversation identity. */
export function continuationSessionId(
  turns: Turn[],
  _sourceMode: "web" | "local" | "hybrid",
  freshRun: boolean,
): string | undefined {
  if (freshRun || turns.length === 0) return undefined;
  const previous = turns[turns.length - 1];
  return previous.status === "completed"
    && previous.sessionId
    ? previous.sessionId
    : undefined;
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

export interface ActivitySegment {
  key: string;
  events: WSEvent[];
  priorEvents: WSEvent[];
  followUp?: { text: string; mode?: string };
}

/** 以真正注入模型的事件为界；队列回执比轨迹先到时只追加临时分界。 */
export function turnActivitySegments(events: WSEvent[], followUps: string[] = []): ActivitySegment[] {
  const segments: ActivitySegment[] = [{ key: "initial", events: [], priorEvents: [] }];
  const prior: WSEvent[] = [];
  let injected = 0;
  for (const event of events) {
    const data = (event.data ?? {}) as Record<string, unknown>;
    if (event.type === "trajectory" && data.type === "harness" && data.kind === "steer_injected") {
      segments.push({
        key: `follow-up-${injected++}`,
        events: [], priorEvents: [...prior],
        followUp: { text: String(data.text ?? ""), mode: String(data.mode ?? "") },
      });
    } else {
      segments[segments.length - 1].events.push(event);
    }
    prior.push(event);
  }
  for (let index = injected; index < followUps.length; index++) {
    segments.push({ key: `follow-up-${index}`, events: [], priorEvents: [...prior],
      followUp: { text: followUps[index] } });
  }
  return segments;
}
