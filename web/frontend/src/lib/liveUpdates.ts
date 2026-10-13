import type { SearchState, WSEvent } from "./types";

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
export function advanceAnswer(cursor: AnswerCursor, events: WSEvent[]): AnswerCursor {
  let { streamId, answer } = cursor;
  for (const event of events) {
    if (event.type !== "trajectory") continue;
    const data = (event.data ?? {}) as Record<string, unknown>;
    if (data.phase !== "final_answer") continue;
    if (data.type === "answer_stream_start") { streamId = String(data.stream_id || ""); answer = ""; }
    else if (data.type === "answer_stream_delta" && streamId && data.stream_id === streamId && typeof data.delta === "string") answer += data.delta;
  }
  return { streamId, answer };
}

export function olderRevision(incoming: string, current: string): boolean {
  if (!incoming || !current) return false;
  const a = incoming.split("-"); const b = current.split("-");
  if (a.length !== 5 || b.length !== 5) return false;
  return BigInt(`0x${a[2]}`) < BigInt(`0x${b[2]}`);
}
