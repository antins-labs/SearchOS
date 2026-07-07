// Derived views over the raw event stream + search state, shared by the
// inline orchestration card and the execution drawer. Pure functions only.

import type { SearchState, WSEvent } from "./types";
import type { WorkerInfo } from "@/hooks/useSearch";

/** Rebuild per-sub-agent cards from a full event list (used when replaying a
 *  loaded historical session — mirrors the incremental updater in useSearch).
 *  `final` (session is done) coerces any agent left "running" to completed —
 *  a finished run has nothing still in flight. */
export function foldWorkers(events: WSEvent[], final = false): WorkerInfo[] {
  const map = new Map<string, WorkerInfo>();
  for (const e of events) {
    const etype = String(e.type || "");
    if (etype !== "trajectory" && !etype.startsWith("blackboard.")) continue;
    const data = (e.data ?? {}) as Record<string, unknown>;
    const agent = String(data.agent || data.worker || data.agent_name || "");
    if (!agent || agent === "orchestrator") continue;
    const prev = map.get(agent);
    const dtype = String(data.type || "");
    const status = String(data.status || "");
    let next: WorkerInfo["status"] = prev?.status ?? "running";
    if (dtype === "agent_complete" || dtype === "agent_final" || status === "completed" || status === "partial") next = "completed";
    if (dtype === "agent_error" || dtype === "error" || status === "error") next = "error";
    map.set(agent, {
      name: agent,
      intent: prev?.intent ?? (agent.startsWith("warmup") ? "explore" : agent.startsWith("writer") ? "write" : "search"),
      scope: prev?.scope ?? agent,
      status: next,
      events: prev ? [...prev.events, e] : [e],
    });
  }
  const out = [...map.values()];
  if (final) {
    for (const w of out) {
      if (w.status === "running" || w.status === "pending") w.status = "completed";
    }
  }
  return out;
}

export const PHASES = [
  { key: "warmup", label: "warmup" },
  { key: "schema", label: "schema" },
  { key: "dispatch", label: "dispatch" },
  { key: "evaluate", label: "evaluate" },
  { key: "synthesize", label: "synthesize" },
] as const;

export type PhaseKey = (typeof PHASES)[number]["key"];

/** Furthest phase the orchestrator has reached, inferred from the feed. */
export function derivePhase(
  events: WSEvent[],
  status: "idle" | "running" | "completed" | "error",
): { reached: number; current: PhaseKey } {
  let reached = 0; // warmup by default once anything runs
  for (const e of events) {
    if (e.type !== "trajectory") continue;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = String(d.type || "");
    const tool = String(d.tool || "");
    const action =
      typeof d.action === "string" ? d.action.match(/'name':\s*'([^']+)'/)?.[1] : "";

    if (tool === "create_schema" || action === "create_schema") reached = Math.max(reached, 1);
    if (t === "dispatch" || action === "enqueue_tasks") reached = Math.max(reached, 2);
    if (tool === "evaluate_progress") reached = Math.max(reached, 3);
    if (tool === "synthesize_answer") reached = Math.max(reached, 4);
  }
  if (status === "completed") reached = 4;
  return { reached, current: PHASES[Math.min(reached, 4)].key };
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
