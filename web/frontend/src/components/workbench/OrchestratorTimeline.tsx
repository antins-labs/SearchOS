"use client";

import { useState, type ComponentType, type ReactNode } from "react";
import {
  Users, LayoutGrid, BarChart3, FileCheck, Eye, Compass, Search, BookOpen, CheckCircle2,
  Loader2, Maximize2, MessageSquarePlus, TriangleAlert,
} from "lucide-react";
import type { WSEvent } from "@/lib/types";
import { agentLabel } from "./trace";
import ToolCallDetailDialog, { type ToolCallDetail } from "./ToolCallDetailDialog";

/* The orchestrator's own run trajectory: each step is a card — its reasoning
 * (thinking) on top, the action it took as a small coloured chip below. A
 * fan-out (consecutive dispatch events) collapses into ONE card listing every
 * sub-agent launched in that concurrent wave, by codename. */

type Icon = ComponentType<{ size?: number; className?: string }>;

interface DispatchAgent { name: string; task: string }
interface CheckAgent { name: string; status: string }

interface ActionView {
  icon: Icon;
  label: string;
  tone: string;
  detail?: string;
  agents?: DispatchAgent[]; // dispatch wave
  checks?: CheckAgent[];    // check_agents report
  result?: string;          // tool observation preview
  spin?: boolean;           // in-flight (tool_call_started, no step yet)
  toolCall?: ToolCallDetail;
}

const STR = (v: unknown) => (typeof v === "string" ? v : "");

function actionName(raw: unknown): string {
  if (raw && typeof raw === "object") return STR((raw as Record<string, unknown>).name);
  return STR(raw).match(/'name':\s*'([^']+)'/)?.[1] ?? "";
}
function actionArgs(raw: unknown): string {
  if (raw && typeof raw === "object") {
    const a = (raw as Record<string, unknown>).args;
    return typeof a === "string" ? a : JSON.stringify(a ?? "");
  }
  return STR(raw);
}
const trim = (t: string, n = 120) => (t.length > n ? t.slice(0, n) + "…" : t);

const CHIP = {
  accent: "bg-accent/12 text-accent-ink",
  clay: "bg-clay/70 text-accent-ink",
  ok: "bg-ok/15 text-ok",
  error: "bg-err/10 text-err",
  neutral: "bg-surface-2 text-ink-dim",
} as const;

const STATUS_DOT: Record<string, string> = {
  completed: "bg-ok", partial: "bg-ok", running: "bg-accent", error: "bg-err",
};

function stepView(name: string, args: string): ActionView | null {
  switch (name) {
    case "create_schema": {
      const tbl = args.match(/"table_label"\s*:\s*"([^"]+)"/)?.[1];
      return { icon: LayoutGrid, tone: CHIP.clay, label: "Built coverage schema", detail: tbl };
    }
    case "evaluate_progress":
      return { icon: BarChart3, tone: CHIP.clay, label: "Evaluated coverage" };
    case "synthesize_answer":
      return { icon: FileCheck, tone: CHIP.ok, label: "Synthesized answer" };
    case "search_and_read":
    case "search":
      return { icon: Search, tone: CHIP.neutral, label: "Searched", detail: args.match(/'query':\s*'([^']*)'/)?.[1] };
    case "open":
      return { icon: BookOpen, tone: CHIP.neutral, label: "Read a page" };
    case "enqueue_tasks":
      return null; // represented by the dispatch wave that follows
    default:
      return name ? { icon: Compass, tone: CHIP.neutral, label: name } : null;
  }
}

interface Card { k: number; reasoning: string; action: ActionView | null; }

const RUNNING_LABEL: Record<string, string> = {
  check_agents: "Checking on sub-agents",
  evaluate_progress: "Evaluating coverage",
  synthesize_answer: "Synthesizing answer",
  create_schema: "Building coverage schema",
  enqueue_tasks: "Queueing tasks",
};

function buildCards(
  events: WSEvent[],
  status: "idle" | "running" | "completed" | "error",
  priorEvents: WSEvent[],
): Card[] {
  const out: Card[] = [];
  const pending: { id: string; index: unknown; tool: string; card: Card }[] = [];
  const live = new Map<string, string>();
  let legacyWave: Card | null = null;
  const trackWorker = (event: WSEvent) => {
    if (event.type !== "trajectory") return;
    const d = (event.data ?? {}) as Record<string, unknown>;
    const agent = STR(d.agent), type = STR(d.type);
    if (!agent || agent === "orchestrator") return;
    if (type === "dispatch") live.set(agent, "running");
    if (type === "agent_final" || type === "agent_complete") live.set(agent, "completed");
    if (type === "agent_error" || type === "error") live.set(agent, "error");
  };
  priorEvents.forEach(trackWorker);
  const runningAgents = () => [...live].filter(([, s]) => s === "running")
    .map(([name, workerStatus]) => ({ name, status: workerStatus }));
  const finishPending = () => {
    for (const call of pending.splice(0)) {
      if (!call.card.action) continue;
      call.card.action = { ...call.card.action, icon: Compass, spin: false,
        label: `${call.tool} · 已结束，未收到结果`,
        toolCall: call.card.action.toolCall && { ...call.card.action.toolCall, status: undefined },
      };
    }
  };

  events.forEach((e, i) => {
    if (e.type !== "trajectory") return;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = STR(d.type), agent = STR(d.agent);
    trackWorker(e);

    if (t === "task_complete" || t === "task_error") {
      finishPending();
      out.push({ k: i, reasoning: "", action: {
        icon: t === "task_complete" ? CheckCircle2 : TriangleAlert,
        tone: t === "task_complete" ? CHIP.ok : CHIP.error,
        label: t === "task_complete" ? "Finished & synthesized" : "运行未完成",
      } });
      return;
    }
    if (t === "dispatch" && agent) {
      const owner = [...pending].reverse().find((p) => p.tool === "enqueue_tasks")?.card;
      const card = owner ?? legacyWave ?? { k: i, reasoning: "", action: {
        icon: Users, tone: CHIP.accent, label: "", agents: [],
      } };
      if (!owner && !legacyWave) { out.push(card); legacyWave = card; }
      if (card.action) {
        const agents = [...(card.action.agents ?? []), { name: agent, task: trim(STR(d.task)) }];
        card.action = { ...card.action, agents,
          label: owner ? `正在派发 ${agents.length} 个代理…`
            : agents.length > 1 ? `Dispatched ${agents.length} agents (concurrent)` : "Dispatched 1 agent",
        };
      }
      return;
    }
    if (t === "harness" && STR(d.kind) === "steer_injected") {
      legacyWave = null;
      out.push({ k: i, reasoning: "", action: {
        icon: MessageSquarePlus, tone: CHIP.accent,
        label: STR(d.mode) === "after_tool" ? "工具返回后已加入追问" : "已加入立即引导",
        detail: trim(STR(d.text), 140),
      } });
      return;
    }
    if (agent !== "orchestrator") return;
    if (t === "tool_call_started") {
      if (d.tool_call_id && pending.some((call) => call.id === d.tool_call_id)) return;
      legacyWave = null;
      const tool = STR(d.tool);
      const card: Card = { k: i, reasoning: STR(d.reasoning).trim(), action: {
        icon: Loader2, spin: true, tone: CHIP.neutral,
        label: `${RUNNING_LABEL[tool] ?? tool}…`,
        toolCall: { tool, arguments: actionArgs({ args: d.args }), output: "", agent,
          timestamp: STR(d.timestamp), status: "running" },
      } };
      out.push(card);
      pending.push({ id: STR(d.tool_call_id), index: d.step_index, tool, card });
      return;
    }
    if (t !== "step" && t !== "tool_call_failed") return;
    const failed = t === "tool_call_failed" || d.status === "error";
    const name = t === "step" ? actionName(d.action) : STR(d.tool);
    const args = t === "step" ? actionArgs(d.action) : actionArgs({ args: d.args });
    const id = STR(d.tool_call_id);
    const match = pending.findIndex((call) => id ? call.id === id
      : d.step_index != null && call.index != null ? call.index === d.step_index : call.tool === name);
    const started = match >= 0 ? pending.splice(match, 1)[0].card : null;
    const card = started ?? (name === "enqueue_tasks" ? legacyWave : null)
      ?? { k: i, reasoning: "", action: null };
    if (!started && card !== legacyWave) out.push(card);
    const agents = card.action?.agents;
    const fullResult = STR(d.observation || d.observation_summary || d.error).trim();
    let action: ActionView | null;
    if (failed) {
      action = { icon: TriangleAlert, tone: CHIP.error,
        label: `${name} · ${d.status === "cancelled" ? "已取消" : "调用失败"}` };
    } else if (name === "enqueue_tasks") {
      action = { icon: Users, tone: CHIP.accent, agents,
        label: agents?.length ? agents.length > 1 ? `Dispatched ${agents.length} agents (concurrent)`
          : "Dispatched 1 agent" : "Tasks queued" };
    } else if (name === "check_agents") {
      const checks = runningAgents();
      action = { icon: Eye, tone: CHIP.neutral, checks,
        label: checks.length ? `Checked ${checks.length} in-flight agents` : "Checked on sub-agents" };
    } else action = stepView(name, args);
    if (action) {
      action.result = name === "enqueue_tasks" && agents?.length && !failed
        ? undefined : trim(fullResult, 220);
      action.toolCall = { tool: name, arguments: args, output: fullResult, agent,
        timestamp: card.action?.toolCall?.timestamp || STR(d.timestamp),
        status: failed ? d.status === "cancelled" ? "cancelled" : "error" : "completed" };
    }
    card.reasoning = STR(d.reasoning).trim() || card.reasoning;
    card.action = action;
    legacyWave = null;
  });
  if (status === "completed" || status === "error") finishPending();
  else for (const call of pending) {
    if (call.tool === "check_agents" && call.card.action) call.card.action.checks = runningAgents();
  }
  return out;
}

export default function OrchestratorTimeline({ events, status = "running", priorEvents = [] }: {
  events: WSEvent[];
  status?: "idle" | "running" | "completed" | "error";
  priorEvents?: WSEvent[];
}) {
  const cards = buildCards(events, status, priorEvents);
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const selectedTool = cards.find((card) => card.k === selectedKey)?.action?.toolCall ?? null;
  if (cards.length === 0) {
    return <div className="px-4 py-3 text-[12.5px] text-ink-faint">Orchestrator is starting…</div>;
  }
  return (
    <div className="space-y-2 px-4 py-3">
      {cards.map((c) => (
        <div key={c.k} className="rise-in surface rounded-xl px-3.5 py-3">
          {c.reasoning && <p className="mb-2.5 line-clamp-4 text-[13px] leading-relaxed text-ink">{c.reasoning}</p>}
          {c.action && (
              <ActionBlock action={c.action} onOpenTool={() => setSelectedKey(c.k)}>
                <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
                  <c.action.icon size={13} className={c.action.spin ? "animate-spin" : undefined} />
                  {c.action.label}
                  {c.action.detail && <span className="font-normal opacity-80">· {c.action.detail}</span>}
                  {c.action.toolCall && <Maximize2 className="ml-auto shrink-0 opacity-60" size={12} />}
                </div>

                {/* tool result preview */}
                {c.action.result && (
                  <div className="mt-1.5 line-clamp-3 font-mono text-[11px] font-normal leading-relaxed opacity-75">
                    ⎿ {c.action.result}
                  </div>
                )}

                {/* dispatch wave — codename + task per concurrent agent */}
                {c.action.agents && c.action.agents.length > 0 && (
                  <ul className="mt-2 space-y-1.5">
                    {c.action.agents.map((a, ai) => (
                      <li key={ai} className="flex gap-2 text-[11.5px] font-normal leading-snug">
                        <span className="shrink-0 font-mono font-medium text-accent-ink">{agentLabel(a.name)}</span>
                        <span className="line-clamp-2 text-ink-dim">{a.task}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {/* check report — codename + status per agent */}
                {c.action.checks && c.action.checks.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {c.action.checks.map((a, ai) => (
                      <span key={ai} className="flex items-center gap-1.5 rounded-md bg-paper px-2 py-1 font-mono text-[11px] text-ink-dim">
                        <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[a.status] ?? "bg-ink-faint"}`} />
                        {agentLabel(a.name)}
                      </span>
                    ))}
                  </div>
                )}
              </ActionBlock>
          )}
        </div>
      ))}
      <ToolCallDetailDialog detail={selectedTool} onClose={() => setSelectedKey(null)} />
    </div>
  );
}

function ActionBlock({
  action,
  onOpenTool,
  children,
}: {
  action: ActionView;
  onOpenTool: (detail: ToolCallDetail) => void;
  children: ReactNode;
}) {
  const className = `w-full rounded-lg px-3 py-2 text-left ${action.tone}`;
  if (!action.toolCall) return <div className={className}>{children}</div>;
  return (
    <button
      type="button"
      onClick={() => onOpenTool(action.toolCall!)}
      aria-label={`View full parameters and output for ${action.toolCall.tool}`}
      className={`${className} transition-[filter] hover:brightness-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40`}
    >
      {children}
    </button>
  );
}
