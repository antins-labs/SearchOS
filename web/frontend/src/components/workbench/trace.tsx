"use client";

import { Maximize2 } from "lucide-react";

import type { WSEvent, EvidenceNode } from "@/lib/types";
import type { ToolCallDetail } from "./ToolCallDetailDialog";

/* ── agent naming ──────────────────────────────────────────────
   Backend names the first search agent `search_agent` (no suffix),
   then `search_agent_2`, `_3`… Normalise to a stable number/label. */
export function agentNum(name: string): string {
  const m = name.match(/_(\d+)$/);
  if (m) return m[1];
  if (name === "search_agent") return "1";
  return "";
}

export function agentLabel(name: string): string {
  if (name.startsWith("explore") || name.startsWith("warmup")) return "Explore";
  if (name.startsWith("writer")) return "Writer";
  if (name.startsWith("search_agent")) {
    const n = agentNum(name);
    return n ? `Agent ${n}` : "Agent";
  }
  return name;
}

/* ── action parsing ────────────────────────────────────────────
   `data.action` arrives as a Python-repr string, e.g.
   "{'name': 'search', 'args': \"{'query': 'gpu pricing'}\"}".
   Pull out the tool name and its primary argument. */
export function actionInfo(e: WSEvent): { name: string; arg: string } {
  const d = (e.data ?? {}) as Record<string, unknown>;
  const raw = d.action;
  let s = "";
  let name = "";
  if (typeof raw === "string") {
    s = raw;
  } else if (raw && typeof raw === "object") {
    name = String((raw as Record<string, unknown>).name || "");
    const a = (raw as Record<string, unknown>).args;
    s = typeof a === "string" ? a : JSON.stringify(a ?? "");
  }
  if (!name) {
    name =
      s.match(/'name':\s*'([^']+)'/)?.[1] ||
      (d.type === "orchestrator_tool" ? String(d.tool || "") : "") ||
      "";
  }
  let batchArg = "";
  if (name === "explore_web") {
    try {
      const parsed = JSON.parse(s) as { queries?: unknown[] };
      if (Array.isArray(parsed.queries)) batchArg = `${parsed.queries.length} query paths`;
    } catch {
      const queryList = s.match(/["']queries["']\s*:\s*\[([^\]]*)\]/)?.[1] || "";
      const count = (queryList.match(/https?:\/\/|["'][^"']+["']/g) || []).length;
      if (count) batchArg = `${count} query paths`;
    }
  }
  const arg = batchArg ||
    s.match(/'query':\s*'([^']*)'/)?.[1] ||
    s.match(/'pattern':\s*'([^']*)'/)?.[1] ||
    s.match(/'id_or_url':\s*'([^']*)'/)?.[1] ||
    "";
  return { name, arg };
}

/** Clean the observation: drop the "[Now viewing]" chrome and line-count
 *  noise, return the first meaningful line (a page title / result). */
export function cleanObs(e: WSEvent): string {
  const d = (e.data ?? {}) as Record<string, unknown>;
  let o = String(d.observation || d.observation_summary || d.result_preview || "");
  if (!o) return "";
  o = o.replace(/^\[Now viewing\]\s*/i, "");
  const lines = o
    .split("\n")
    .map((l) => l.trim())
    .filter(
      (l) =>
        l &&
        !/^\*\*viewing lines/i.test(l) &&
        !/^L\d+:?$/.test(l) &&
        !/^URL:\s*search:\/\//i.test(l),
    );
  return lines[0] || "";
}

const VERB: Record<string, string> = {
  explore_web: "Exploring wave",
  search: "Searching",
  open: "Reading",
  find: "Finding",
  enqueue_tasks: "Queueing tasks",
  check_agents: "Checking agents",
  create_schema: "Building schema",
};

/** Tidy an arg for display: find patterns arrive as `["a","b"]` — strip the
 *  JSON brackets/quotes down to `a, b`. URLs/queries pass through. */
function prettyArg(arg: string): string {
  if (!arg) return "";
  if (arg.trim().startsWith("[")) {
    return arg.replace(/[[\]"]/g, "").replace(/\s*,\s*/g, ", ").trim();
  }
  return arg;
}

/** verb + human detail for a single step. */
function stepText(e: WSEvent): { verb: string; detail: string } | null {
  const { name, arg } = actionInfo(e);
  if (!name) return null;
  const a = prettyArg(arg);
  // For `open` the arg is just a result index; the page title (obs) is useful.
  const detail = name === "open" ? cleanObs(e) || a : a || cleanObs(e);
  return { verb: VERB[name] || name, detail };
}

export interface Step {
  verb: string;
  detail: string;
}

function rawActionArgs(event: WSEvent): string {
  const data = (event.data ?? {}) as Record<string, unknown>;
  if (data.type === "orchestrator_tool") {
    return typeof data.args === "string"
      ? data.args
      : JSON.stringify(data.args ?? "");
  }
  const action = data.action;
  if (action && typeof action === "object") {
    const args = (action as Record<string, unknown>).args;
    return typeof args === "string" ? args : JSON.stringify(args ?? "");
  }
  return typeof action === "string" ? action : "";
}

/** Full payload behind a rendered tool step. */
export function toolCallDetail(event: WSEvent): ToolCallDetail | null {
  if (event.type !== "trajectory") return null;
  const data = (event.data ?? {}) as Record<string, unknown>;
  const type = String(data.type || "");
  if (type !== "step" && type !== "orchestrator_tool") return null;
  const { name } = actionInfo(event);
  if (!name) return null;
  return {
    tool: name,
    arguments: rawActionArgs(event),
    output: String(
      data.observation || data.result || data.observation_summary || data.result_preview || "",
    ),
    agent: String(data.agent || ""),
    timestamp: String(data.timestamp || ""),
  };
}

/** Recent steps for an agent, newest last, collapsing consecutive duplicates
 *  (e.g. paging through the same page yields the same title repeatedly). */
export function recentSteps(events: WSEvent[], n: number): Step[] {
  const all: Step[] = [];
  for (const e of events) {
    if (e.type !== "trajectory") continue;
    const t = String((e.data as Record<string, unknown>)?.type || "");
    if (t !== "step" && t !== "dispatch") continue;
    const s = stepText(e);
    if (!s) continue;
    const last = all[all.length - 1];
    if (last && last.verb === s.verb && last.detail === s.detail) continue;
    all.push(s);
  }
  return all.slice(-n);
}

/** The orchestrator's instruction to this agent (from its dispatch event). */
export function agentGoal(events: WSEvent[]): string {
  for (const e of events) {
    if (e.type !== "trajectory") continue;
    const d = (e.data ?? {}) as Record<string, unknown>;
    if (d.type === "dispatch" && d.task) return String(d.task);
  }
  return "";
}

/** One line in a full trace log. Returns null for events we don't render. */
export function TraceLine({
  event,
  onOpenTool,
}: {
  event: WSEvent;
  onOpenTool?: (detail: ToolCallDetail) => void;
}) {
  if (event.type === "trajectory") {
    const d = (event.data ?? {}) as Record<string, unknown>;
    const t = String(d.type || "");

    if (t === "dispatch") {
      return (
        <div className="text-accent-ink dark:text-accent-ink">→ dispatch {String(d.agent || "")}</div>
      );
    }
    // agent_complete is redundant with agent_final — render only the latter,
    // including its closing summary (the agent's answer).
    if (t === "agent_complete") return null;
    if (t === "agent_final") {
      const r = String(d.reasoning || "").trim();
      return (
        <div className="text-ok dark:text-ok">
          ✓ finished
          {r && <span className="text-ink-dim"> — {r.slice(0, 200)}</span>}
        </div>
      );
    }
    if (t === "step" || t === "orchestrator_tool") {
      const s = stepText(event);
      if (!s) return null;
      const detail = toolCallDetail(event);
      const content = (
        <>
          <span className="text-accent-ink dark:text-accent">{s.verb}</span>
          {s.detail && <span className="text-ink-dim"> {s.detail}</span>}
          {detail && onOpenTool && (
            <Maximize2 className="ml-auto shrink-0 text-ink-faint" size={11} />
          )}
        </>
      );
      if (!detail || !onOpenTool) return <div className="leading-relaxed">{content}</div>;
      return (
        <button
          type="button"
          onClick={() => onOpenTool(detail)}
          aria-label={`View full parameters and output for ${detail.tool}`}
          className="flex w-full items-start gap-1 rounded-md px-1.5 py-1 text-left leading-relaxed transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          {content}
        </button>
      );
    }
    return null;
  }

  if (event.type === "evidence_added") {
    const node = (event as Record<string, unknown>).node as EvidenceNode | undefined;
    return (
      <div className="text-ok dark:text-ok">
        + evidence: {String(node?.claim || "").slice(0, 120)}
      </div>
    );
  }

  return null;
}
