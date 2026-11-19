// Derived views over the raw event stream + search state, shared by the
// inline orchestration card and the execution drawer. Pure functions only.

import type { SearchState, WorkerInfo, WSEvent } from "./types";
import { cellRef } from "@/lib/socmRefs";

export function deriveRunPhase(events: WSEvent[], agent = "orchestrator"): string | null {
  let phase: string | null = null;
  for (const event of events) {
    const data = event.type === "trajectory" && event.data && typeof event.data === "object"
      ? event.data as Record<string, unknown> : event as unknown as Record<string, unknown>;
    const type = String(data.type ?? event.type);
    if (["search_completed", "search_error"].includes(type)) phase = null;
    if (String(data.agent ?? "orchestrator") !== agent) continue;
    if (["task_complete", "task_error"].includes(type)) phase = null;
    if (data.kind === "run_phase") {
      phase = data.status === "running" ? String(data.phase) : null;
    } else if (["tool_call_started", "agent_final", "agent_complete", "agent_error"].includes(type)) {
      phase = null;
    }
    if (type === "generation_started") phase = String(data.phase || "generating");
    if (type === "question") phase = "waiting_user";
    if (type === "question_answered") phase = "generating";
  }
  return phase;
}

export function runPhaseLabel(phase: string | null): string | null {
  return ({ initializing: "正在初始化…", loading_skills: "正在准备检索能力…",
    routing: "正在选择检索方式…", generating: "正在生成下一步行动或回答…",
    waiting_user: "等待你的选择…" } as Record<string, string>)[phase ?? ""] ?? null;
}

export interface LocalRunProgress {
  present: boolean;
  phase: "retrieving" | "answering" | "completed" | "limited" | "error";
  documentCount: number;
  evidenceCount: number;
  readCount: number;
  citationCount: number;
}

export function deriveLocalRunProgress(events: WSEvent[]): LocalRunProgress {
  let present = false;
  let phase: LocalRunProgress["phase"] = "retrieving";
  let documentCount = 0;
  let evidenceCount = 0;
  let readCount = 0;
  let citationCount = 0;

  for (const event of events) {
    const data = event.type === "trajectory" && event.data && typeof event.data === "object"
      ? event.data as Record<string, unknown>
      : event as unknown as Record<string, unknown>;
    const sourceMode = String(data.source_mode ?? "");
    const type = String(data.type ?? event.type ?? "");
    if (sourceMode === "local") present = true;
    if (present && typeof data.document_count === "number") documentCount = data.document_count;
    if (event.type === "evidence_added") evidenceCount += 1;
    if (present && typeof data.evidence_count === "number") evidenceCount = data.evidence_count;
    if (present && typeof data.read_count === "number") {
      readCount = data.read_count;
      if (readCount > 0) phase = "answering";
    }
    if (present && typeof data.citation_count === "number") citationCount = data.citation_count;
    if (present && type === "task_complete") {
      phase = data.reading_stop_reason === "budget" || data.reading_stop_reason === "timeout"
        ? "limited" : "completed";
    }
    if (present && (type === "task_error" || event.type === "search_error")) phase = "error";
  }

  return { present, phase, documentCount, evidenceCount, readCount, citationCount };
}

/** 实时和历史回放共用同一个不可变事件 reducer。 */
export function foldWorkers(events: WSEvent[], final = false, terminalStatus: "completed" | "error" = "completed"): WorkerInfo[] {
  const workers = updateWorkersBatch([], events);
  return final ? finalizeWorkers(workers, terminalStatus) : workers;
}

export function finalizeWorkers(workers: WorkerInfo[], terminalStatus: "completed" | "error" = "completed"): WorkerInfo[] {
  return workers.map((worker) =>
    worker.status === "running" || worker.status === "pending"
      ? { ...worker, status: terminalStatus }
      : worker,
  );
}

export function updateWorkers(current: WorkerInfo[], event: WSEvent): WorkerInfo[] {
  return updateWorkersBatch(current, [event]);
}

/** Clone each affected worker's history once per burst or replay. */
export function updateWorkersBatch(current: WorkerInfo[], events: WSEvent[]): WorkerInfo[] {
  const copy = [...current];
  const indexes = new Map(current.map((worker, index) => [worker.name, index]));
  const touched = new Set<string>();
  for (const event of events) {
    const etype = String(event.type || "");
    const isTraj = etype === "trajectory";
    const isBlackboard = etype.startsWith("blackboard.");
    if (!isTraj && !isBlackboard) continue;

    const data = (event.data ?? {}) as Record<string, unknown>;
    const agent = String(data.agent || data.worker || data.agent_name || "");
    if (!agent || agent === "orchestrator") continue;

    // 保持不可变，避免 React 重复执行 updater 时累加事件。
    const idx = indexes.get(agent) ?? -1;
    const prev = idx >= 0 ? copy[idx] : null;

    const dtype = String(data.type || "");
    const status = String(data.status || "");
    const toolEvent = ["step", "tool_call_started", "tool_call_failed", "skill_execution"].includes(dtype);
    let nextStatus = prev?.status ?? "running";
    const phaseEvent = data.kind === "run_phase";
    if (dtype === "dispatch" || dtype === "tool_call_started" || (phaseEvent && status === "running")) {
      nextStatus = "running";
    }
    if (dtype === "agent_complete" || dtype === "task_complete" || (!toolEvent && !phaseEvent && (status === "completed" || status === "partial"))) {
      nextStatus = "completed";
    }
    if (dtype === "agent_error" || dtype === "error" || (!toolEvent && !phaseEvent && status === "error")) {
      nextStatus = "error";
    }

    const updated: WorkerInfo = {
      name: agent,
      intent:
        prev?.intent ??
        ((agent.startsWith("explore") || agent.startsWith("warmup"))
          ? "explore"
          : agent.startsWith("writer") ? "write" : "search"),
      scope: prev?.scope ?? agent,
      status: nextStatus,
      events: prev ? (touched.has(agent) ? prev.events : [...prev.events]) : [],
    };

    updated.events.push(event);
    touched.add(agent);
    if (idx >= 0) copy[idx] = updated;
    else { indexes.set(agent, copy.length); copy.push(updated); }
  }
  return touched.size ? copy : current;
}

/** Filled vs total cells across the coverage map (the live progress bar).
 *  Excludes the "_default" placeholder table's cells. */
export function deriveCoverage(state: SearchState | null): { filled: number; total: number } {
  const cells = Object.entries(state?.coverage_map?.cells ?? {})
    .filter(([k]) => !cellRef(k).table_id.startsWith("_"))
    .map(([, c]) => c);
  const filled = cells.filter((c) => c.status === "filled").length;
  return { filled, total: cells.length };
}

/** Active vs candidate evidence counts for stall diagnosis. */
export function deriveEvidenceBreakdown(state: SearchState | null): {
  active: number;
  candidate: number;
  total: number;
} {
  const nodes = state?.evidence_graph?.nodes ?? [];
  let active = 0;
  let candidate = 0;
  for (const node of nodes) {
    const status = String(node.status ?? "");
    if (status === "active") active += 1;
    else if (status === "candidate") candidate += 1;
  }
  return { active, candidate, total: nodes.length };
}

export interface SkillExecutionInfo {
  executionId: string;
  parentCallId: string;
  parentExecutionId: string;
  skill: string;
  argv: unknown;
  status: "running" | "completed" | "error" | "cancelled";
  output: string;
}

/** 子执行使用明确的父 ID；历史记录从已保存的参数中恢复同一关系。 */
export function skillExecutionInfo(data: Record<string, unknown>): SkillExecutionInfo | null {
  const action = data.action as { args?: Record<string, unknown> } | undefined;
  const args = (action?.args ?? data.args ?? {}) as Record<string, unknown>;
  const current = data.type === "skill_execution";
  if (!current && !(["step", "tool_call_started", "tool_call_failed"].includes(String(data.type)) && args.parent_execution_id)) return null;
  const source = current ? data : args;
  const status = String(data.status ?? "");
  return {
    executionId: String(current ? data.execution_id : data.tool_call_id),
    parentCallId: String(data.parent_tool_call_id ?? ""),
    parentExecutionId: String(source.parent_execution_id ?? ""),
    skill: String(source.skill ?? ""), argv: source.argv ?? [],
    status: data.type === "tool_call_started" || status === "running" ? "running"
      : status === "cancelled" ? "cancelled"
      : data.type === "tool_call_failed" || ["error", "failed", "timed_out", "blocked"].includes(status) ? "error" : "completed",
    output: String(data.observation ?? data.error ?? ""),
  };
}

/** 只统计 Agent 发起的工具调用，技能子步骤归入父 Exec。 */
export function deriveStepCount(events: WSEvent[]): number {
  const ids = new Set<string>();
  for (const [index, e] of events.entries()) {
    if (e.type !== "trajectory") continue;
    const data = (e.data ?? {}) as Record<string, unknown>;
    if (skillExecutionInfo(data)) continue;
    if (["step", "tool_call_started", "tool_call_failed"].includes(String(data.type))) {
      ids.add(`${data.agent}:${data.tool_call_id || (data.step_index ?? index)}`);
    }
  }
  return ids.size;
}

/** The synthesized answer text, if the run produced one. Prefers the writer's
 *  final summary, then the synthesize_answer tool preview, then any agent_final. */
export function deriveAnswer(events: WSEvent[]): string {
  let writerFinal = "";
  let synth = "";
  let lastFinal = "";
  for (const e of events) {
    if (e.type !== "trajectory") continue;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = String(d.type || "");
    const agent = String(d.agent || "");
    if (t === "agent_final") {
      const r = String(d.reasoning || "").trim();
      if (r) {
        lastFinal = r;
        if (agent.startsWith("writer")) writerFinal = r;
      }
    }
    if (t === "orchestrator_tool" && String(d.tool) === "synthesize_answer") {
      const p = String(d.result_preview || "").trim();
      if (p) synth = p;
    }
  }
  return writerFinal || synth || lastFinal;
}

/** 全量恢复沿用增量事件的同一折叠规则。 */
export function deriveLiveAnswer(events: WSEvent[]): string | null {
  const { streamId, answer } = advanceAnswer({ streamId: "", answer: "" }, events);
  return streamId ? answer : null;
}

export interface StateChange { op: "set" | "delete" | "append"; path: string[]; value?: unknown }

/** Copy only modified branches; the previous snapshot stays immutable. */
export function applyStateChanges(state: SearchState, changes: StateChange[]): SearchState {
  const update = (value: unknown, change: StateChange, depth: number): unknown => {
    if (depth === change.path.length) {
      if (change.op === "append") {
        if (!Array.isArray(value) || !Array.isArray(change.value)) throw new Error("Invalid append delta");
        return [...value, ...change.value];
      }
      return change.value;
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid delta path");
    const key = change.path[depth];
    const next = { ...value } as Record<string, unknown>;
    if (change.op === "delete" && depth === change.path.length - 1) delete next[key];
    else Object.defineProperty(next, key, { value: update(next[key], change, depth + 1), enumerable: true, writable: true, configurable: true });
    return next;
  };
  return changes.reduce((current, change) => update(current, change, 0) as SearchState, state);
}

export interface AnswerCursor { streamId: string; answer: string }
/** 非空 stream_id 统一转为字符串；空 ID 无法接收增量。 */
export function advanceAnswer(cursor: AnswerCursor, events: WSEvent[]): AnswerCursor {
  let { streamId, answer } = cursor;
  for (const event of events) {
    if (event.type !== "trajectory") continue;
    const data = (event.data ?? {}) as Record<string, unknown>;
    if (data.phase !== "final_answer") continue;
    const id = String(data.stream_id || "");
    if (data.type === "answer_stream_start") { streamId = id; answer = ""; }
    else if (data.type === "answer_stream_delta" && streamId && id === streamId && typeof data.delta === "string") answer += data.delta;
  }
  return { streamId, answer };
}

export function olderRevision(incoming: string, current: string): boolean {
  if (!incoming || !current) return false;
  const a = incoming.split("-"); const b = current.split("-");
  if (a.length !== 5 || b.length !== 5) return false;
  return BigInt(`0x${a[2]}`) < BigInt(`0x${b[2]}`);
}
