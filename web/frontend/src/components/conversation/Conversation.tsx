"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, ChevronDown, Layers3, Loader2, Search, Wrench, WifiOff } from "lucide-react";
import Composer, { type SubmitOpts } from "@/components/shell/Composer";
import OrchestrationCard from "./OrchestrationCard";
import Answer, { cleanAnswer } from "./Answer";
import AnswerActions from "./AnswerActions";
import CoverageTable from "@/components/coverage/CoverageTable";
import ResultExportMenu from "@/components/coverage/ResultExportMenu";
import type { Turn } from "@/lib/conversation";
import type { CoverageCell, RepairCellTarget } from "@/lib/types";

interface Props {
  turns: Turn[];
  running: boolean;
  reconnecting?: boolean;
  stopping?: boolean;
  onSubmit: (q: string, opts: SubmitOpts) => void;
  onSteer?: (text: string) => void;
  onStop?: () => void;
  onRerun: (query: string) => void;
  onRepair: (turn: Turn, cells: RepairCellTarget[]) => void;
  onOpenDrawer: (turnId: string) => void;
  registerTurnRef?: (id: string, el: HTMLDivElement | null) => void;
  focusRequest?: number;
}

export default function Conversation({ turns, running, reconnecting = false, stopping = false, onSubmit, onSteer, onStop, onRerun, onRepair, onOpenDrawer, registerTurnRef, focusRequest = 0 }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [composerFocusRequest, setComposerFocusRequest] = useState(0);
  const repairSource = [...turns].reverse().find((turn) => (
    turn.status === "completed" && !!turn.sessionId && !!turn.searchState
  ));
  // Follow the bottom only while a search is live; a freshly loaded historical
  // session should rest at the top, not jump to its references.
  useEffect(() => {
    if (running) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, running]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[760px] px-3 pb-6 pt-16 sm:px-5 min-[1180px]:px-6 min-[1180px]:py-8">
          {turns.map((t, index) => (
            <TurnView
              key={t.id}
              turn={t}
              onOpen={() => onOpenDrawer(t.id)}
              onRerun={() => onRerun(t.query)}
              onRepairCells={!running && repairSource?.id === t.id
                ? (cells) => onRepair(t, cells)
                : undefined}
              onContinue={index === turns.length - 1 && t.status === "completed"
                ? () => setComposerFocusRequest((value) => value + 1)
                : undefined}
              runDisabled={running}
              registerRef={registerTurnRef ? (el) => registerTurnRef(t.id, el) : undefined}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {reconnecting && (
        <div role="status" aria-live="polite" className="border-t border-warn/30 bg-warn/5 px-3 py-2 text-[12.5px] text-ink-dim sm:px-5">
          <div className="mx-auto flex max-w-[712px] items-center gap-2">
            <WifiOff className="shrink-0 text-warn" size={14} />
            <span className="min-w-0 flex-1">Connection interrupted. Research is still running while SearchOS reconnects.</span>
            <Loader2 className="shrink-0 animate-spin text-warn" size={14} />
          </div>
        </div>
      )}

      <div className="border-t border-line bg-paper">
        <div className="mx-auto max-w-[760px] px-3 py-3 sm:px-5 min-[1180px]:px-6 min-[1180px]:py-4">
          <Composer onSubmit={onSubmit} onSteer={onSteer} onStop={onStop} running={running} stopping={stopping} focusRequest={composerFocusRequest + focusRequest} variant="bar" />
        </div>
      </div>
    </div>
  );
}

function TurnView({
  turn,
  onOpen,
  onRerun,
  onContinue,
  onRepairCells,
  runDisabled,
  registerRef,
}: {
  turn: Turn;
  onOpen: () => void;
  onRerun: () => void;
  onContinue?: () => void;
  onRepairCells?: (cells: RepairCellTarget[]) => void;
  runDisabled: boolean;
  registerRef?: (el: HTMLDivElement | null) => void;
}) {
  const [answerCollapsed, setAnswerCollapsed] = useState(false);
  const done = turn.status === "completed";
  const displayAnswer = cleanAnswer(turn.answer);
  const answerCollapsible = displayAnswer.length > 1600 || displayAnswer.split("\n").length > 28;
  const hasTable = Object.keys(turn.searchState?.coverage_map?.cells ?? {}).some((k) => !k.startsWith("_"));
  const tableStateLabel = turn.stateSource === "snapshot"
    ? "Turn snapshot"
    : turn.stateSource === "latest"
      ? "Latest session state"
      : null;

  return (
    <div ref={registerRef} className="mb-10 scroll-mt-6 last:mb-2">
      {/* user message */}
      <div className="mb-6 flex justify-end">
        <div className="max-w-[90%] rounded-2xl rounded-br-md border border-line bg-surface px-4 py-2.5 text-[15px] leading-relaxed text-ink sm:max-w-[80%]">
          {turn.query}
        </div>
      </div>

      {/* live follow-ups steered into this turn mid-run */}
      {(turn.followUps ?? []).map((f, i) => (
        <div key={i} className="rise-in -mt-3 mb-6 flex justify-end">
          <div className="max-w-[80%] rounded-2xl rounded-br-md border border-accent/30 bg-clay/40 px-4 py-2.5">
            <div className="mb-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-accent-ink">
              Steered mid-run
            </div>
            <div className="text-[14px] leading-relaxed text-ink">{f}</div>
          </div>
        </div>
      ))}

      {/* assistant turn */}
      <div className="flex gap-2.5 sm:gap-3.5">
        <div className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent font-serif text-[12px] font-semibold text-white sm:h-7 sm:w-7 sm:text-[14px]">
          S
        </div>
        <div className="min-w-0 flex-1">
          {/* Restored earlier turns carry no per-turn trajectory — plain Q&A. */}
          {(turn.events.length > 0 || turn.status === "running") && (
            <div className="mb-4">
              <OrchestrationCard
                events={turn.events}
                searchState={turn.searchState}
                status={turn.status}
                workers={turn.workers}
                onOpen={onOpen}
              />
            </div>
          )}

          {turn.error && (
            <p className="mb-4 rounded-lg border border-err/30 bg-err/5 px-3 py-2 text-[13px] text-err">{turn.error}</p>
          )}

          {turn.repair && (
            <RepairSummary turn={turn} />
          )}

          {done && displayAnswer && (
            <div className="mb-5">
              <div className={answerCollapsed ? "max-h-[320px] overflow-hidden" : undefined}>
                <Answer markdown={displayAnswer} />
              </div>
              <AnswerActions
                query={turn.query}
                markdown={displayAnswer}
                collapsible={answerCollapsible}
                collapsed={answerCollapsed}
                onToggleCollapse={() => setAnswerCollapsed((value) => !value)}
                onRerun={onRerun}
                onContinue={onContinue}
                runDisabled={runDisabled}
              />
            </div>
          )}

          {done && hasTable && (
            <div className="mb-4 overflow-hidden rounded-xl border border-line">
              <div className="flex items-center justify-between gap-3 border-b border-line bg-surface-2 px-3.5 py-2">
                <span className="font-serif text-[14px] font-semibold text-ink">Final table</span>
                <div className="flex items-center gap-2">
                  {tableStateLabel && <span className="hidden text-[11px] text-ink-faint sm:inline">{tableStateLabel}</span>}
                  <ResultExportMenu turn={turn} answer={displayAnswer} />
                </div>
              </div>
              <div>
                <CoverageTable
                  coverageMap={turn.searchState?.coverage_map ?? null}
                  evidence={turn.searchState?.evidence_graph?.nodes ?? []}
                  onRepairCells={onRepairCells}
                  animationScope={turn.id}
                />
              </div>
            </div>
          )}

          {done && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-dim">
              {typeof turn.meta.coverageScore === "number" && (
                <span>Coverage <b className="font-semibold text-ink">{(turn.meta.coverageScore * 100).toFixed(0)}%</b></span>
              )}
              {typeof turn.meta.evidenceCount === "number" && (
                <span>Evidence <b className="font-semibold text-ink">{turn.meta.evidenceCount}</b></span>
              )}
              {typeof turn.meta.elapsed === "number" && (
                <span>Time <b className="font-semibold text-ink">{turn.meta.elapsed.toFixed(1)}s</b></span>
              )}
              {turn.meta.verdict && <span className="text-ink-faint">{turn.meta.verdict}</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const REPAIR_STATUS: Record<CoverageCell["status"], { label: string; className: string }> = {
  missing: { label: "Missing", className: "text-ink-faint" },
  uncertain: { label: "Uncertain", className: "text-warn" },
  hard_cell: { label: "Hard", className: "text-err" },
  filled: { label: "Filled", className: "text-ok" },
};

function compactValue(value: CoverageCell["value"] | undefined): string {
  if (Array.isArray(value)) return value.join(", ") || "--";
  return value || "--";
}

function RepairSummary({ turn }: { turn: Turn }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const state = turn.searchState;
  const repair = turn.repair;
  if (!repair) return null;

  const primaryTable = Object.keys(state?.coverage_map?.tables ?? {})[0] ?? "_default";
  const previousEvidence = new Set(repair.evidenceIdsBefore);
  const newEvidence = (state?.evidence_graph?.nodes ?? []).filter((node) => !previousEvidence.has(node.id));
  const rows = repair.cells.map((target) => {
    const key = `${target.table_id}/${target.entity}.${target.attribute}`;
    const current = state?.coverage_map?.cells[key];
    const evidenceCount = newEvidence.filter((node) => (
      (node.table_id || primaryTable) === target.table_id
      && node.entity === target.entity
      && node.attribute === target.attribute
    )).length;
    const changed = !!current && (
      current.status !== target.before.status
      || JSON.stringify(current.value) !== JSON.stringify(target.before.value)
    );
    return { target, current, evidenceCount, changed };
  });
  const filled = rows.filter((row) => row.current?.status === "filled").length;
  const remaining = rows.length - filled;
  const changed = rows.filter((row) => row.changed).length;
  const evidenceCount = rows.reduce((sum, row) => sum + row.evidenceCount, 0);
  const largeRepair = rows.length > 8;
  const progress = rows.length ? Math.round((filled / rows.length) * 100) : 0;
  const orderedRows = largeRepair
    ? [...rows].sort((a, b) => {
        const aFilled = a.current?.status === "filled" ? 1 : 0;
        const bFilled = b.current?.status === "filled" ? 1 : 0;
        return aFilled - bFilled || Number(b.changed) - Number(a.changed);
      })
    : rows;
  const unresolvedPreview = orderedRows.filter((row) => row.current?.status !== "filled").slice(0, 3);
  const showRows = !largeRepair || detailsOpen;

  return (
    <section className="mb-5 border-y border-line py-3" aria-label="Repair results">
      <div className="flex flex-wrap items-center gap-2">
        <Wrench className="text-accent-ink" size={15} />
        <h3 className="text-[13px] font-semibold text-ink">Targeted repair</h3>
        {repair.planner && (
          <span className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-faint">
            {repair.planner === "orchestrator"
              ? "Orchestrator planned"
              : repair.planner === "llm" ? "LLM planned" : "Safe fallback"}
            {repair.planner !== "orchestrator" && typeof repair.planningLatencyMs === "number"
              ? ` · ${repair.planningLatencyMs} ms`
              : ""}
          </span>
        )}
        {turn.status === "running" && <Loader2 className="ml-auto animate-spin text-accent-ink" size={14} />}
      </div>

      <div className="mt-3">
        <div
          role="progressbar"
          aria-label="Repair completion"
          aria-valuemin={0}
          aria-valuemax={rows.length}
          aria-valuenow={filled}
          className="h-1.5 overflow-hidden rounded-full bg-surface-2"
        >
          <div className="h-full rounded-full bg-ok transition-[width] duration-300" style={{ width: `${progress}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-ink-dim">
          <span><b className="font-semibold text-ok">{filled}</b> filled</span>
          <span><b className={`font-semibold ${remaining ? "text-warn" : "text-ink"}`}>{remaining}</b> remaining</span>
          <span><b className="font-semibold text-ink">{changed}</b> changed</span>
          <span><b className="font-semibold text-ink">{evidenceCount}</b> new {evidenceCount === 1 ? "source" : "sources"}</span>
          <span className="ml-auto tabular-nums text-ink-faint">{progress}%</span>
        </div>
      </div>

      {largeRepair && !detailsOpen && unresolvedPreview.length > 0 && (
        <div className="mt-2.5 flex min-w-0 items-center gap-2 text-[11px] text-ink-faint">
          <Search size={12} className="shrink-0 text-warn" />
          <span className="shrink-0">Needs attention</span>
          <span className="min-w-0 truncate text-ink-dim">
            {unresolvedPreview.map(({ target }) => `${target.entity} · ${target.attribute}`).join("  /  ")}
          </span>
          {remaining > unresolvedPreview.length && <span className="shrink-0">+{remaining - unresolvedPreview.length}</span>}
        </div>
      )}

      {largeRepair && (
        <button
          type="button"
          aria-expanded={detailsOpen}
          onClick={() => setDetailsOpen((value) => !value)}
          className="mt-3 flex w-full items-center gap-2 border-t border-line pt-2.5 text-left text-[12px] text-ink-dim transition-colors hover:text-ink"
        >
          <Layers3 size={13} className="text-accent-ink" />
          <span>{detailsOpen ? "Hide cell details" : `View ${rows.length} cell details`}</span>
          {!detailsOpen && remaining > 0 && <span className="text-warn">{remaining} unresolved</span>}
          <ChevronDown size={14} className={`ml-auto text-ink-faint transition-transform ${detailsOpen ? "rotate-180" : ""}`} />
        </button>
      )}

      {showRows && (
        <div className={`divide-y divide-line ${largeRepair ? "mt-2 max-h-[360px] overflow-y-auto pr-1" : "mt-2.5"}`}>
        {orderedRows.map(({ target, current, evidenceCount: cellEvidence, changed: cellChanged }) => {
          const beforeStatus = REPAIR_STATUS[target.before.status];
          const afterStatus = REPAIR_STATUS[current?.status ?? target.before.status];
          return (
            <div key={`${target.table_id}/${target.entity}.${target.attribute}`} className="grid gap-1 py-2 text-[12px] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-3">
              <div className="min-w-0">
                <div className="truncate font-medium text-ink" title={`${target.table_id} / ${target.entity} / ${target.attribute}`}>
                  {target.entity} · {target.attribute}
                </div>
                <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-ink-dim">
                  <span className={beforeStatus.className}>{beforeStatus.label}</span>
                  <ArrowRight className="shrink-0 text-ink-faint" size={12} />
                  <span className={afterStatus.className}>{afterStatus.label}</span>
                  {cellChanged && current && (
                    <span className="min-w-0 truncate text-ink-faint" title={compactValue(current.value)}>
                      {compactValue(target.before.value)} → {compactValue(current.value)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-ink-dim">
                {current?.status === "filled" ? <CheckCircle2 className="text-ok" size={13} /> : <Search className="text-ink-faint" size={13} />}
                {cellEvidence} new {cellEvidence === 1 ? "source" : "sources"}
              </div>
            </div>
          );
        })}
        </div>
      )}
    </section>
  );
}
