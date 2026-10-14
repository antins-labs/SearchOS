"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, ArrowRight, Ban, ShieldCheck, Sparkles, Compass, FileSearch, Files, MessageSquareText, TriangleAlert, X } from "lucide-react";
import type { SearchState, WSEvent } from "@/lib/types";
import { deriveCoverage, deriveLocalRunProgress, deriveStepCount } from "@/lib/derive";
import OrchestratorTimeline from "@/components/workbench/OrchestratorTimeline";
import { deriveExploreProgress, type ExploreProgress } from "@/lib/exploreProgress";

export interface WorkerLite {
  name: string;
  status: "pending" | "running" | "completed" | "error";
}

interface Props {
  events: WSEvent[];
  priorEvents?: WSEvent[];
  continued?: boolean;
  searchState: SearchState | null;
  status: "idle" | "running" | "completed" | "error";
  workers: WorkerLite[];
  sourceMode?: "web" | "local" | "hybrid";
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
export default function OrchestrationCard({ events, priorEvents = [], continued = false, searchState, status, workers, sourceMode, onOpen }: Props) {
  const running = status === "running";
  const { filled, total } = deriveCoverage(searchState);
  const steps = deriveStepCount(events);
  const active = workers.filter((w) => w.status === "running").length;
  const doneAgents = workers.filter((w) => w.status === "completed").length;
  const runDetails = deriveRunDetails(events);
  const explore = deriveExploreProgress(events);
  const localProgress = deriveLocalRunProgress(events);
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

  const displayedAgents = running ? active || workers.length : status === "error" ? workers.length : doneAgents || workers.length;

  if (sourceMode === "local" || localProgress.present) {
    return (
      <LocalSearchCard
        open={open}
        onToggle={() => setOpen((value) => !value)}
        onOpen={onOpen}
        status={status}
        libraryScope={searchState?.source_scope?.selection === "library"}
        documentCount={localProgress.documentCount}
        readCount={localProgress.readCount || localProgress.evidenceCount}
        citationCount={localProgress.citationCount}
        limited={localProgress.phase === "limited"}
      />
    );
  }

  return (
    <div className="surface overflow-hidden rounded-xl">
      {/* header — click to collapse/expand */}
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 px-4 py-3 text-left">
        {continued ? (
          <MessageSquareText size={15} className="text-ink-faint" />
        ) : running ? (
          <span className="spin-ring h-[13px] w-[13px]" />
        ) : status === "error" ? (
          <span className="grid h-[15px] w-[15px] place-items-center rounded-full bg-err text-white">
            <X size={10} strokeWidth={3} />
          </span>
        ) : (
          <span className="grid h-[15px] w-[15px] place-items-center rounded-full bg-ok text-white">
            <Check size={10} strokeWidth={3} />
          </span>
        )}
        <span className="text-[13px] font-medium text-ink">
          {continued ? "追问前的运行记录" : sourceMode === "hybrid" ? (running ? "Hybrid · 正在检索与核实" : status === "error" ? "Hybrid · 运行未完成" : "Hybrid · 运行记录") : status === "error" ? "Research incomplete" : running && explore.present && explore.phase !== "completed"
            ? "Exploring information landscape"
            : running ? "Orchestrating search" : "Orchestration trace"}
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

      {sourceMode === "hybrid" && Object.entries(searchState?.source_scope?.unavailable_sources ?? {}).map(([source, reason]) => (
        <p key={source} className="border-t border-line px-4 py-2 text-xs text-ink-dim">
          {reason}
        </p>
      ))}

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
          {explore.present && <ExploreProgressPanel progress={explore} />}
          <OrchestratorTimeline events={events} status={status} priorEvents={priorEvents} />
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

function LocalSearchCard({ open, onToggle, onOpen, status, libraryScope, documentCount, readCount, citationCount, limited }: {
  open: boolean;
  onToggle: () => void;
  onOpen: () => void;
  status: Props["status"];
  libraryScope: boolean;
  documentCount: number;
  readCount: number;
  citationCount: number;
  limited: boolean;
}) {
  const running = status === "running";
  const failed = status === "error";
  const selectedLabel = libraryScope
    ? "按问题检索当前知识库"
    : documentCount > 0 ? `已锁定 ${documentCount} 份资料` : "正在确认资料范围";

  return (
    <div className="surface overflow-hidden rounded-xl border-accent/15">
      <button type="button" aria-expanded={open} onClick={onToggle} className="flex w-full items-center gap-2.5 px-4 py-3 text-left">
        {running ? (
          <span className="spin-ring h-[13px] w-[13px]" />
        ) : failed ? (
          <span className="grid h-[15px] w-[15px] place-items-center rounded-full bg-err text-white"><X size={10} strokeWidth={3} /></span>
        ) : limited ? (
          <TriangleAlert size={15} className="text-warn" />
        ) : (
          <span className="grid h-[15px] w-[15px] place-items-center rounded-full bg-ok text-white"><Check size={10} strokeWidth={3} /></span>
        )}
        <span className="text-[13px] font-medium text-ink">
          {running ? readCount > 0 ? "正在生成本地回答" : "正在检索本地资料" : failed ? "本地资料问答失败" : limited ? "已基于已读内容回答 · 阅读受限" : "本地资料回答已生成"}
        </span>
        <span className="ml-auto text-[12px] text-ink-dim">
          {documentCount > 0 && <><b className="font-semibold text-ink">{documentCount}</b> 份资料</>}
          {documentCount > 0 && readCount > 0 && <span className="px-1 text-ink-faint">·</span>}
          {readCount > 0 && <><b className="font-semibold text-ink">{readCount}</b> 个阅读片段</>}
        </span>
        <ChevronDown size={16} className={`text-ink-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="space-y-2 border-t border-line bg-paper/40 px-4 py-3 text-[12px]">
          <LocalStage icon={<Files size={14} />} label={selectedLabel} state={libraryScope || documentCount > 0 ? "done" : "active"} />
          <LocalStage
            icon={<FileSearch size={14} />}
            label={readCount > 0 ? `已读取 ${readCount} 个原文片段` : running ? "正在查找相关原文" : "没有读到可用原文"}
            state={readCount > 0 ? "done" : running ? "active" : failed ? "error" : "idle"}
          />
          <LocalStage
            icon={<MessageSquareText size={14} />}
            label={running ? "围绕问题组织回答" : failed ? "回答生成未完成" : citationCount > 0 ? `回答引用了 ${citationCount} 个来源` : "回答未附可核查引用"}
            state={running ? readCount > 0 ? "active" : "idle" : failed ? "error" : "done"}
          />
        </div>
      )}

      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-1 border-t border-line px-4 py-2 text-[12px] text-accent-ink transition-colors hover:bg-surface-2"
      >
        查看原文与运行记录
        <ArrowRight size={13} />
      </button>
    </div>
  );
}

function LocalStage({ icon, label, state }: {
  icon: ReactNode;
  label: string;
  state: "idle" | "active" | "done" | "error";
}) {
  return (
    <div className={`flex items-center gap-2 ${state === "idle" ? "text-ink-faint" : state === "error" ? "text-err" : "text-ink-dim"}`}>
      <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-md ${state === "done" ? "bg-ok/10 text-ok" : state === "active" ? "bg-accent/10 text-accent-ink" : state === "error" ? "bg-err/10 text-err" : "bg-surface-2"}`}>
        {state === "active" ? <span className="spin-ring h-3 w-3" /> : state === "done" ? <Check size={13} /> : icon}
      </span>
      <span>{label}</span>
    </div>
  );
}

function ExploreProgressPanel({ progress }: { progress: ExploreProgress }) {
  const active = progress.phase === "running" || progress.phase === "planning";
  const currentWave = Math.min(progress.wavesCompleted + (progress.phase === "running" ? 1 : 0), progress.maxWaves);
  const currentWaveTarget = currentWave > progress.minWaves ? progress.maxWaves : progress.minWaves;
  const detail = progress.mode === "legacy"
    ? progress.phase === "completed"
      ? `Legacy Explore completed · ${progress.legacySteps} browser steps`
      : progress.currentTool
        ? `Running ${progress.currentTool} · ${progress.legacySteps} steps completed`
        : `Planning the next browser step · ${progress.legacySteps} completed`
    : progress.phase === "completed"
      ? `${progress.wavesCompleted} waves · ${progress.queriesCompleted} queries · ${progress.pagesOpened} pages opened`
      : progress.phase === "running"
        ? `Wave ${currentWave}/${currentWaveTarget} · ${progress.currentQueries} query paths searching and opening pages in parallel`
        : progress.phase === "analyzing"
          ? `Wave ${progress.wavesCompleted}/${progress.minWaves} complete · analyzing coverage gaps`
          : "Designing orthogonal query families for broad recall";

  return (
    <div className="border-b border-line px-4 py-3">
      <div className="flex items-center gap-2">
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${active ? "bg-accent/10 text-accent-ink" : "bg-surface-2 text-ink-dim"}`}>
          {active ? <span className="spin-ring h-3 w-3" /> : <Compass size={14} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[12.5px] font-medium text-ink">Explore</span>
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] capitalize text-ink-dim">
              {progress.phase}
            </span>
          </div>
          <p className="mt-0.5 truncate text-[11.5px] text-ink-dim" title={detail}>{detail}</p>
        </div>
        {progress.mode === "batch" && (
          <div className="flex shrink-0 items-center gap-1" aria-label={`${progress.wavesCompleted} Explore waves completed`}>
            {Array.from({ length: progress.maxWaves }, (_, index) => {
              const wave = index + 1;
              const done = wave <= progress.wavesCompleted;
              const live = progress.phase === "running" && wave === currentWave;
              return <span key={wave} className={`h-1.5 w-5 rounded-full ${done ? "bg-ok" : live ? "bg-accent animate-pulse" : "bg-line-strong"}`} />;
            })}
          </div>
        )}
      </div>
    </div>
  );
}
