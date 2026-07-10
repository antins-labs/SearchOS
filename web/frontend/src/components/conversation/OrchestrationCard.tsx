"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, ArrowRight, Ban, ShieldCheck, Sparkles } from "lucide-react";
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

function deriveRunDetails(events: WSEvent[]) {
  const skills = new Set<string>();
  let trustedDomains: string[] = [];
  let excludedDomains: string[] = [];

  for (const event of events) {
    const data = event.type === "trajectory" && event.data && typeof event.data === "object"
      ? event.data as Record<string, unknown>
      : event;
    const type = String(data.type ?? "");
    if (type === "run_config") {
      trustedDomains = Array.isArray(data.trusted_domains)
        ? data.trusted_domains.filter((value): value is string => typeof value === "string")
        : [];
      excludedDomains = Array.isArray(data.excluded_domains)
        ? data.excluded_domains.filter((value): value is string => typeof value === "string")
        : [];
    }
    if (type === "dispatch" && Array.isArray(data.skills)) {
      data.skills.forEach((value) => { if (typeof value === "string" && value) skills.add(value); });
    }
    if (type === "step" && data.action && typeof data.action === "object") {
      const name = (data.action as { name?: unknown }).name;
      if (typeof name === "string" && name.startsWith("skill_") && name.length > 6) {
        skills.add(name.slice(6));
      }
    }
  }
  return { skills: Array.from(skills), trustedDomains, excludedDomains };
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
  const runDetails = deriveRunDetails(events);
  const visibleSkills = runDetails.skills.slice(0, 3);
  const hasRunDetails = runDetails.skills.length > 0
    || runDetails.trustedDomains.length > 0
    || runDetails.excludedDomains.length > 0;

  const [open, setOpen] = useState(status !== "completed");
  const collapsedOnce = useRef(false);
  useEffect(() => {
    if (status === "completed" && !collapsedOnce.current) {
      collapsedOnce.current = true;
      const frame = window.requestAnimationFrame(() => setOpen(false));
      return () => window.cancelAnimationFrame(frame);
    }
  }, [status]);

  const displayedAgents = running ? active || workers.length : doneAgents || workers.length;

  return (
    <div className="surface overflow-hidden rounded-xl">
      {/* header — click to collapse/expand */}
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 px-4 py-3 text-left">
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
          <b className="font-semibold text-ink">{displayedAgents}</b> {displayedAgents === 1 ? "agent" : "agents"}
          <span className="px-1 text-ink-faint">·</span>
          <b className="font-semibold text-ink">{steps}</b> {steps === 1 ? "step" : "steps"}
          {total > 0 && (
            <>
              <span className="px-1 text-ink-faint">·</span>
              <b className="font-semibold text-ink">{filled}/{total}</b> {total === 1 ? "cell" : "cells"}
            </>
          )}
        </span>
        <ChevronDown size={16} className={`text-ink-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {hasRunDetails && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-4 py-2 text-[10.5px] text-ink-dim">
          {runDetails.skills.length > 0 && (
            <span className="flex min-w-0 items-center gap-1.5" title={runDetails.skills.join(", ")}>
              <Sparkles size={11} className="shrink-0 text-accent-ink" />
              <span className="text-ink-faint">Skills</span>
              {visibleSkills.map((skill) => (
                <span key={skill} className="max-w-28 truncate font-mono text-ink">{skill}</span>
              ))}
              {runDetails.skills.length > visibleSkills.length && (
                <span className="tabular-nums text-ink-faint">+{runDetails.skills.length - visibleSkills.length}</span>
              )}
            </span>
          )}
          {runDetails.trustedDomains.length > 0 && (
            <span className="flex items-center gap-1" title={runDetails.trustedDomains.join(", ")}>
              <ShieldCheck size={11} className="text-ok" />
              <span>{runDetails.trustedDomains.length} trusted</span>
            </span>
          )}
          {runDetails.excludedDomains.length > 0 && (
            <span className="flex items-center gap-1" title={runDetails.excludedDomains.join(", ")}>
              <Ban size={11} className="text-err" />
              <span>{runDetails.excludedDomains.length} excluded</span>
            </span>
          )}
        </div>
      )}

      {/* body — the orchestrator trajectory */}
      {open && (
        <div className="border-t border-line bg-paper/40">
          <OrchestratorTimeline events={events} />
        </div>
      )}

      {/* footer — into the detail drawer */}
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-1 border-t border-line px-4 py-2 text-[12px] text-accent-ink transition-colors hover:bg-surface-2"
      >
        View agents &amp; evidence
        <ArrowRight size={13} />
      </button>
    </div>
  );
}
