"use client";

import type { WSEvent } from "@/lib/types";
import { Loader2, CheckCircle2, XCircle, Circle, ChevronRight } from "lucide-react";
import { agentLabel, recentSteps, agentGoal } from "./trace";

export interface AgentCardData {
  name: string;
  intent: string;
  scope: string;
  status: "pending" | "running" | "completed" | "error";
  events: WSEvent[];
}

const STATUS_ICON = {
  pending: <Circle size={12} className="text-ink-faint" />,
  running: <Loader2 size={12} className="animate-spin text-accent dark:text-accent" />,
  completed: <CheckCircle2 size={12} className="text-ok dark:text-ok" />,
  error: <XCircle size={12} className="text-err dark:text-err" />,
} as const;

const RING = {
  pending: "",
  running: "ring-1 ring-accent/30 dark:ring-accent/25",
  completed: "",
  error: "ring-1 ring-err/25",
} as const;

export default function AgentCard({
  data,
  onClick,
}: {
  data: AgentCardData;
  onClick: () => void;
}) {
  const { name, status, events } = data;
  const steps = recentSteps(events, 2);
  const goal = agentGoal(events);
  const stepCount = events.filter((e) => e.type === "trajectory" && (e.data as Record<string, unknown>)?.type === "step").length;

  return (
    <button
      onClick={onClick}
      className={`surface rise-in group flex h-full min-h-[8rem] w-full flex-col overflow-hidden rounded-lg text-left transition-all hover:-translate-y-0.5 hover:shadow-lg ${RING[status]}`}
    >
      {/* header */}
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        {STATUS_ICON[status]}
        <span className="truncate text-xs font-semibold text-accent-ink dark:text-accent">
          {agentLabel(name)}
        </span>
        <span className="ml-auto text-[10px] capitalize text-ink-faint">
          {status}
        </span>
      </div>

      {/* body — goal + latest activity */}
      <div className="flex-1 space-y-1.5 overflow-hidden px-3 py-2">
        {goal && (
          <p className="line-clamp-2 text-[11px] leading-relaxed text-ink-dim">
            {goal}
          </p>
        )}
        {steps.length > 0 && (
          <div className="space-y-0.5">
            {steps.map((s, i) => (
              <div key={i} className="truncate text-[11px]">
                <span className="text-accent-ink/80 dark:text-accent/80">{s.verb}</span>
                {s.detail && <span className="text-ink-dim"> {s.detail}</span>}
              </div>
            ))}
          </div>
        )}
        {!goal && steps.length === 0 && (
          <span className="text-[11px] text-ink-faint">
            {status === "running" ? "working…" : "no activity"}
          </span>
        )}
      </div>

      {/* footer */}
      <div className="flex items-center justify-between border-t border-line px-3 py-1.5 text-[10px] text-ink-dim">
        <span>{stepCount} {stepCount === 1 ? "step" : "steps"}</span>
        <span className="flex items-center gap-0.5 transition-colors group-hover:text-accent dark:group-hover:text-accent">
          trace <ChevronRight size={11} />
        </span>
      </div>
    </button>
  );
}
