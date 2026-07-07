"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ArrowRight } from "lucide-react";
import type { SearchState, WSEvent } from "@/lib/types";
import { deriveCoverage, deriveStepCount } from "@/lib/derive";
import OrchestratorTimeline from "@/components/workbench/OrchestratorTimeline";

export interface WorkerLite {
  name: string;
  status: "pending" | "running" | "completed" | "error";
}

interface Props {
  events: WSEvent[];
  searchState: SearchState | null;
  status: "idle" | "running" | "completed" | "error";
  workers: WorkerLite[];
  onOpen: () => void;
}

/** The orchestrator's run, as one collapsible card in the conversation: its
 *  think→action trajectory inside, auto-collapsing on completion so the final
 *  answer is what you see. "View agents & evidence" opens the detail drawer. */
export default function OrchestrationCard({ events, searchState, status, workers, onOpen }: Props) {
  const running = status === "running";
  const { filled, total } = deriveCoverage(searchState);
  const steps = deriveStepCount(events);
  const active = workers.filter((w) => w.status === "running").length;
  const doneAgents = workers.filter((w) => w.status === "completed").length;

  const [open, setOpen] = useState(status !== "completed");
  const collapsedOnce = useRef(false);
  useEffect(() => {
    if (status === "completed" && !collapsedOnce.current) {
      collapsedOnce.current = true;
      setOpen(false);
    }
  }, [status]);

  return (
    <div className="surface overflow-hidden rounded-xl">
      {/* header — click to collapse/expand */}
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 px-4 py-3 text-left">
        {running ? (
          <span className="spin-ring h-[13px] w-[13px]" />
        ) : (
          <span className="grid h-[15px] w-[15px] place-items-center rounded-full bg-ok text-white">
            <Check size={10} strokeWidth={3} />
          </span>
        )}
        <span className="text-[13px] font-medium text-ink">
          {running ? "Orchestrating search" : "Orchestration trace"}
        </span>
        <span className="ml-auto text-[12px] text-ink-dim">
          <b className="font-semibold text-ink">{running ? active || workers.length : doneAgents || workers.length}</b> agents
          <span className="px-1 text-ink-faint">·</span>
          <b className="font-semibold text-ink">{steps}</b> steps
          {total > 0 && (
            <>
              <span className="px-1 text-ink-faint">·</span>
              <b className="font-semibold text-ink">{filled}/{total}</b> cells
            </>
          )}
        </span>
        <ChevronDown size={16} className={`text-ink-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* body — the orchestrator trajectory */}
      {open && (
        <div className="border-t border-line bg-paper/40">
          <OrchestratorTimeline events={events} />
        </div>
      )}

      {/* footer — into the detail drawer */}
      <button
        onClick={onOpen}
        className="flex w-full items-center gap-1 border-t border-line px-4 py-2 text-[12px] text-accent-ink transition-colors hover:bg-surface-2"
      >
        View agents &amp; evidence
        <ArrowRight size={13} />
      </button>
    </div>
  );
}
