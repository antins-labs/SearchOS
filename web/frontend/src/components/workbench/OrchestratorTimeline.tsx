"use client";

import type { ComponentType } from "react";
import {
  Users, LayoutGrid, BarChart3, FileCheck, Eye, Compass, Search, BookOpen, CheckCircle2,
} from "lucide-react";
import type { WSEvent } from "@/lib/types";
import { agentLabel } from "./trace";

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

function buildCards(events: WSEvent[]): Card[] {
  const out: Card[] = [];
  let wave: DispatchAgent[] = [];
  let waveKey = -1;
  let pendingReasoning = "";
  const live = new Map<string, string>(); // sub-agent → current status

  const flush = () => {
    if (!wave.length) return;
    out.push({
      k: waveKey,
      reasoning: pendingReasoning,
      action: {
        icon: Users, tone: CHIP.accent,
        label: wave.length > 1 ? `Dispatched ${wave.length} agents (concurrent)` : "Dispatched 1 agent",
        agents: wave,
      },
    });
    wave = [];
    pendingReasoning = "";
  };

  events.forEach((e, i) => {
    if (e.type !== "trajectory") return;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = STR(d.type);
    const agent = STR(d.agent);

    if (t === "dispatch" && agent) {
      if (!wave.length) waveKey = i;
      wave.push({ name: agent, task: trim(STR(d.task)) });
      live.set(agent, "running");
      return;
    }

    // track sub-agent lifecycle so "check" cards can show who's in flight
    if (agent && agent !== "orchestrator") {
      if (t === "agent_final" || t === "agent_complete") live.set(agent, "completed");
      else if (t === "agent_error" || t === "error") live.set(agent, "error");
      return;
    }

    if (agent !== "orchestrator") return;

    if (t === "step") {
      const name = actionName(d.action);
      if (name === "enqueue_tasks") {
        pendingReasoning = STR(d.reasoning).trim() || pendingReasoning;
        return;
      }
      flush();
      if (name === "check_agents") {
        const running = [...live].filter(([, s]) => s === "running").map(([name, status]) => ({ name, status }));
        out.push({
          k: i, reasoning: STR(d.reasoning).trim(),
          action: {
            icon: Eye, tone: CHIP.neutral,
            label: running.length ? `Checked ${running.length} in-flight agents` : "Checked on sub-agents",
            checks: running,
          },
        });
        return;
      }
      out.push({ k: i, reasoning: STR(d.reasoning).trim(), action: stepView(name, actionArgs(d.action)) });
    } else if (t === "agent_final") {
      flush();
      out.push({ k: i, reasoning: STR(d.reasoning).trim(), action: { icon: CheckCircle2, tone: CHIP.ok, label: "Finished & synthesized" } });
    }
  });
  flush();
  return out;
}

export default function OrchestratorTimeline({ events }: { events: WSEvent[] }) {
  const cards = buildCards(events);
  if (cards.length === 0) {
    return <div className="px-4 py-3 text-[12.5px] text-ink-faint">Orchestrator is starting…</div>;
  }
  return (
    <div className="space-y-2 px-4 py-3">
      {cards.map((c) => (
        <div key={c.k} className="rise-in surface rounded-xl px-3.5 py-3">
          {c.reasoning && <p className="mb-2.5 line-clamp-4 text-[13px] leading-relaxed text-ink">{c.reasoning}</p>}
          {c.action && (
            <div className={`rounded-lg px-3 py-2 ${c.action.tone}`}>
              <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
                <c.action.icon size={13} />
                {c.action.label}
                {c.action.detail && <span className="font-normal opacity-80">· {c.action.detail}</span>}
              </div>

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
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
