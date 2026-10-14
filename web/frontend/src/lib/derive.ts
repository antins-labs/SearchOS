// Derived views over the raw event stream + search state, shared by the
// inline orchestration card and the execution drawer. Pure functions only.

import type { SearchState, WorkerInfo, WSEvent } from "./types";

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
    const toolEvent = ["step", "tool_call_started", "tool_call_failed"].includes(dtype);
    let nextStatus = prev?.status ?? "running";
    if (dtype === "agent_complete" || dtype === "task_complete" || (!toolEvent && (status === "completed" || status === "partial"))) {
      nextStatus = "completed";
    }
    if (dtype === "agent_error" || dtype === "error" || (!toolEvent && status === "error")) {
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
    .filter(([k]) => !k.startsWith("_"))
    .map(([, c]) => c);
  const filled = cells.filter((c) => c.status === "filled").length;
  return { filled, total: cells.length };
}

/** Count of `step` events — a live "how much work" signal. */
export function deriveStepCount(events: WSEvent[]): number {
  let n = 0;
  for (const e of events) {
    if (e.type !== "trajectory") continue;
    if (String((e.data as Record<string, unknown>)?.type) === "step") n++;
  }
  return n;
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

/** Fold only committed final-answer events into the visible response. */
export function deriveLiveAnswer(events: WSEvent[]): string | null {
  let streamId = "";
  let answer = "";
  for (const event of events) {
    if (event.type !== "trajectory") continue;
    const data = (event.data ?? {}) as Record<string, unknown>;
    const type = String(data.type || "");
    if (String(data.phase || "") !== "final_answer") continue;
    if (type === "answer_stream_start") {
      streamId = String(data.stream_id || "");
      answer = "";
      continue;
    }
    if (
      type === "answer_stream_delta"
      && streamId
      && String(data.stream_id || "") === streamId
    ) {
      answer += typeof data.delta === "string" ? data.delta : "";
    }
  }
  return streamId ? answer : null;
}
