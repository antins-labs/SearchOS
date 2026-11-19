import type { CoverageCell, ModelDistributionItem, RepairCellTarget, SearchState, SourceSelection, TokenPhaseUsage, TokenUsage, WSEvent } from "./types";
import type { WorkerInfo } from "./types";

export interface RepairCellSnapshot extends RepairCellTarget {
  before: Pick<CoverageCell, "status" | "value">;
}

export interface Turn {
  id: string;
  query: string;
  sessionId: string | null;
  skillGenerationId?: string | null;
  status: "running" | "completed" | "error";
  events: WSEvent[];
  workers: WorkerInfo[];
  searchState: SearchState | null;
  stateSource?: "live" | "snapshot" | "latest" | "unavailable";
  sourceMode?: "web" | "local" | "hybrid";
  /** 提交时保存来源范围，首个后端快照返回前失败也能重试。 */
  sources?: SourceSelection;
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
    extractionPendingTotal?: number;
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
export function restoredRunState(status: "running" | "completed" | "incomplete" | "error" | "waiting_user"):
  { status: Turn["status"]; error: string | null } {
  if (status === "incomplete") return {
    status: "error",
    error: "这次运行已中断，尚未生成最终回答。下方保留的是中间输出和运行记录，可重新运行该问题。",
  };
  if (status === "waiting_user") return { status: "running", error: null };
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

export interface ClarifyQuestion {
  id: string;
  prompt: string;
  options: string[];
  allowMultiple: boolean;
}

export interface ClarifyAnswer {
  id: string;
  selected: string[];
  custom?: string;
}

export interface PendingClarify {
  questionId: string;
  questions: ClarifyQuestion[];
  answers?: ClarifyAnswer[];
}

/** 研究对话里的选择题。已回答的卡片保留选择并禁用。 */
export function clarifyState(events: WSEvent[]): PendingClarify | null {
  let pending: PendingClarify | null = null;
  const answered = new Map<string, ClarifyAnswer[]>();
  for (const event of events) {
    const data = event.type === "trajectory" && event.data && typeof event.data === "object"
      ? event.data as Record<string, unknown> : null;
    if (!data) continue;
    if (data.type === "question" && typeof data.question_id === "string" && Array.isArray(data.questions)) {
      pending = {
        questionId: data.question_id,
        questions: data.questions as ClarifyQuestion[],
      };
    }
    if (data.type === "question_answered" && typeof data.question_id === "string" && Array.isArray(data.answers)) {
      answered.set(data.question_id, data.answers as ClarifyAnswer[]);
    }
  }
  if (!pending) return null;
  const selection = answered.get(pending.questionId);
  return selection ? { ...pending, answers: selection } : pending;
}

export interface ActivitySegment {
  key: string;
  events: WSEvent[];
  priorEvents: WSEvent[];
  followUp?: { text: string; mode?: string };
}

/** 以真正注入模型的事件与澄清作答为界；队列回执比轨迹先到时只追加临时分界。
 *  AskUserQuestion 作答后切分工具体，澄清卡落在前一段助手列内（对齐 JobSeeker）。 */
export function turnActivitySegments(events: WSEvent[], followUps: string[] = []): ActivitySegment[] {
  const segments: ActivitySegment[] = [{ key: "initial", events: [], priorEvents: [] }];
  const prior: WSEvent[] = [];
  let injected = 0;
  let clarifies = 0;
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
      if (event.type === "trajectory" && data.type === "question_answered") {
        const questionId = typeof data.question_id === "string" ? data.question_id : String(clarifies);
        segments.push({
          key: `after-clarify-${questionId}-${clarifies++}`,
          events: [],
          priorEvents: [...prior, event],
        });
      }
    }
    prior.push(event);
  }
  for (let index = injected; index < followUps.length; index++) {
    segments.push({ key: `follow-up-${index}`, events: [], priorEvents: [...prior],
      followUp: { text: followUps[index] } });
  }
  return segments;
}

/** 澄清卡挂在含对应 question 事件的那一段工具块之后。 */
export function clarifyForSegment(
  events: WSEvent[],
  clarify: PendingClarify | null,
): PendingClarify | null {
  if (!clarify) return null;
  for (const event of events) {
    const data = event.type === "trajectory" && event.data && typeof event.data === "object"
      ? event.data as Record<string, unknown> : null;
    if (data?.type === "question" && data.question_id === clarify.questionId) return clarify;
  }
  return null;
}
