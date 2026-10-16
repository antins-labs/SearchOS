import type { MiddlewareComponent } from "./types";

export type TraceKind = "model" | "tool" | "agent";
export type PreviewConditions = Record<string, boolean>;
export interface CallStep {
  id?: string;
  hook: string;
  phase: "before" | "enter" | "call" | "return" | "after";
}

// The insertion slot belongs to the original list, before removing the dragged item.
export function insertMiddleware(selected: string[], id: string, slot: number): string[] {
  const previous = selected.indexOf(id);
  const next = selected.filter((item) => item !== id);
  const index = Math.max(0, Math.min(next.length, slot - (previous >= 0 && previous < slot ? 1 : 0)));
  next.splice(index, 0, id);
  return next;
}

export function assemblyOrderError(selected: string[]): boolean {
  const budget = selected.indexOf("BudgetMiddleware");
  const compaction = selected.indexOf("CompactionContextMiddleware");
  return budget >= 0 && compaction >= 0 && budget > compaction;
}

export function previewMounts(items: MiddlewareComponent[], conditions: PreviewConditions) {
  return items.filter((item) => Object.entries(item.requirements ?? {})
    .every(([key, value]) => conditions[key] === value));
}

/** LangChain runs before hooks forward, after hooks backward, and wrappers inside-out on return. */
export function buildCallChain(items: MiddlewareComponent[], kind: TraceKind): CallStep[] {
  const steps: CallStep[] = [];
  const add = (hook: string, phase: CallStep["phase"], reverse = false) => {
    const matching = items.filter((item) => item.hooks.includes(hook));
    if (reverse) matching.reverse();
    steps.push(...matching.map((item) => ({ id: item.id, hook, phase })));
  };
  if (kind === "agent") {
    add("before_agent", "before");
    steps.push({ hook: "agent_loop", phase: "call" });
    add("after_agent", "after", true);
  } else {
    if (kind === "model") add("before_model", "before");
    const hook = kind === "model" ? "wrap_model_call" : "wrap_tool_call";
    add(hook, "enter");
    steps.push({ hook: kind, phase: "call" });
    add(hook, "return", true);
    if (kind === "model") add("after_model", "after", true);
  }
  return steps;
}
