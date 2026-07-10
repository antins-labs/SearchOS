"use client";

import { useState, type KeyboardEvent } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  GitBranch,
  Loader2,
  Minus,
  Pencil,
  Plus,
} from "lucide-react";

import type { Turn } from "@/lib/conversation";
import { coverageDiffCounts, diffCoverageMaps, type CoverageCellDiff, type CoverageDiffKind } from "@/lib/coverageDiff";
import type { CoverageCell } from "@/lib/types";

interface Props {
  turns: Turn[];
  initialTurnId: string;
  busyTurnId?: string | null;
  onBranch?: (turnId: string, focusComposer: boolean) => Promise<void> | void;
}

const CHANGE_STYLE: Record<CoverageDiffKind, { label: string; className: string; icon: typeof Plus }> = {
  added: { label: "Added", className: "text-ok", icon: Plus },
  modified: { label: "Modified", className: "text-accent-ink", icon: Pencil },
  removed: { label: "Removed", className: "text-err", icon: Minus },
  conflict_resolved: { label: "Conflict resolved", className: "text-ok", icon: CheckCircle2 },
};

function compactValue(cell?: CoverageCell): string {
  if (!cell) return "Not present";
  const value = Array.isArray(cell.value) ? cell.value.join(", ") : cell.value;
  return value || (cell.status === "missing" ? "Missing" : cell.status);
}

function ChangeRow({ change }: { change: CoverageCellDiff }) {
  const style = CHANGE_STYLE[change.kind];
  const Icon = style.icon;
  const before = compactValue(change.before);
  const after = compactValue(change.after);

  return (
    <div className="grid gap-1 border-b border-line px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_minmax(160px,0.8fr)] sm:gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Icon className={`shrink-0 ${style.className}`} size={14} />
          <span className="truncate text-[13px] font-medium text-ink" title={`${change.tableLabel} / ${change.entity} / ${change.attribute}`}>
            {change.entity} · {change.attribute}
          </span>
        </div>
        <div className="ml-[22px] mt-0.5 truncate text-[11px] text-ink-faint">{change.tableLabel}</div>
      </div>
      <div className="ml-[22px] flex min-w-0 items-center gap-1.5 text-[11px] text-ink-dim sm:ml-0 sm:justify-end">
        {change.kind !== "added" && <span className="max-w-[44%] truncate" title={before}>{before}</span>}
        {change.kind === "modified" || change.kind === "conflict_resolved" ? <ArrowRight className="shrink-0 text-ink-faint" size={12} /> : null}
        {change.kind !== "removed" && <span className="max-w-[52%] truncate font-medium text-ink" title={after}>{after}</span>}
      </div>
    </div>
  );
}

export default function VersionsPanel({ turns, initialTurnId, busyTurnId = null, onBranch }: Props) {
  const initialIndex = Math.max(0, turns.findIndex((turn) => turn.id === initialTurnId));
  const [selectedIndex, setSelectedIndex] = useState(initialIndex);
  const [showAll, setShowAll] = useState(false);

  const selected = turns[selectedIndex];
  const previous = selectedIndex > 0 ? turns[selectedIndex - 1] : null;
  const changes = selected?.searchState && previous?.searchState
    ? diffCoverageMaps(previous.searchState.coverage_map, selected.searchState.coverage_map)
    : [];
  const counts = coverageDiffCounts(changes);
  const visibleChanges = showAll ? changes : changes.slice(0, 24);
  const selectedBusy = selected?.id === busyTurnId;
  const canBranch = !!selected?.sessionId && !!selected.searchState && selected.status === "completed" && !!onBranch;

  const onVersionKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % turns.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + turns.length) % turns.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = turns.length - 1;
    else return;
    event.preventDefault();
    setSelectedIndex(next);
    setShowAll(false);
    document.getElementById(`research-version-${next}`)?.focus();
  };

  if (!selected) return <div className="p-4 text-[13px] text-ink-faint">No research versions yet</div>;

  return (
    <div className="min-w-0">
      <div className="border-b border-line px-4 py-3">
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-ink-faint">Research timeline</div>
        <div role="tablist" aria-label="Research versions" className="flex gap-1.5 overflow-x-auto pb-1">
          {turns.map((turn, index) => {
            const selectedVersion = index === selectedIndex;
            const hasSnapshot = !!turn.searchState;
            return (
              <button
                key={turn.id}
                id={`research-version-${index}`}
                type="button"
                role="tab"
                aria-selected={selectedVersion}
                tabIndex={selectedVersion ? 0 : -1}
                title={turn.query}
                onClick={() => { setSelectedIndex(index); setShowAll(false); }}
                onKeyDown={(event) => onVersionKeyDown(event, index)}
                className={`flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-[12px] transition-colors ${
                  selectedVersion
                    ? "border-accent/50 bg-accent-soft font-medium text-ink"
                    : "border-line bg-paper text-ink-dim hover:border-line-strong hover:text-ink"
                }`}
              >
                {hasSnapshot ? <Check size={12} /> : <span className="h-1.5 w-1.5 rounded-full bg-ink-faint" />}
                V{index + 1}
              </button>
            );
          })}
        </div>
      </div>

      <div className="border-b border-line px-4 py-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-[12px] font-semibold text-accent-ink">
            V{selectedIndex + 1}
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="line-clamp-2 text-[13px] font-semibold leading-5 text-ink">{selected.query}</h3>
            <p className="mt-0.5 text-[11px] text-ink-faint">
              {selected.stateSource === "unavailable" ? "Snapshot unavailable" : selectedIndex === 0 ? "Baseline snapshot" : `Compared with V${selectedIndex}`}
            </p>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canBranch || !!busyTurnId}
            onClick={() => void onBranch?.(selected.id, true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-ink px-3 text-[12px] font-medium text-paper transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {selectedBusy ? <Loader2 className="animate-spin" size={13} /> : <GitBranch size={13} />}
            Continue from here
          </button>
          <button
            type="button"
            disabled={!canBranch || !!busyTurnId}
            onClick={() => void onBranch?.(selected.id, false)}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-[12px] font-medium text-ink transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Copy size={13} />
            Copy as new
          </button>
        </div>
      </div>

      {!selected.searchState ? (
        <div className="p-4 text-[13px] leading-5 text-ink-dim">This historical turn predates version snapshots, so its table cannot be compared or branched.</div>
      ) : selectedIndex === 0 ? (
        <div className="p-4">
          <div className="text-[13px] font-medium text-ink">Initial research baseline</div>
          <div className="mt-1 text-[12px] text-ink-dim">
            {Object.keys(selected.searchState.coverage_map.cells ?? {}).length} cells across {Object.keys(selected.searchState.coverage_map.tables ?? {}).length} tables
          </div>
        </div>
      ) : !previous?.searchState ? (
        <div className="p-4 text-[13px] leading-5 text-ink-dim">V{selectedIndex} has no snapshot, so changes for this step cannot be reconstructed.</div>
      ) : (
        <>
          <div className="grid grid-cols-2 border-b border-line sm:grid-cols-4">
            {([
              ["added", counts.added],
              ["modified", counts.modified],
              ["removed", counts.removed],
              ["conflict_resolved", counts.conflict_resolved],
            ] as [CoverageDiffKind, number][]).map(([kind, count]) => {
              const style = CHANGE_STYLE[kind];
              return (
                <div key={kind} className="border-b border-line px-3 py-2.5 last:border-b-0 odd:border-r sm:border-b-0 sm:border-r sm:last:border-r-0">
                  <div className={`text-[16px] font-semibold tabular-nums ${count ? style.className : "text-ink-faint"}`}>{count}</div>
                  <div className="mt-0.5 truncate text-[10px] uppercase tracking-wider text-ink-faint">{style.label}</div>
                </div>
              );
            })}
          </div>
          {changes.length === 0 ? (
            <div className="flex items-center gap-2 p-4 text-[13px] text-ink-dim">
              <CheckCircle2 className="text-ok" size={16} />
              No cell-level changes in this version
            </div>
          ) : (
            <div>
              {visibleChanges.map((change) => <ChangeRow key={`${change.kind}:${change.key}`} change={change} />)}
              {changes.length > 24 && (
                <button
                  type="button"
                  onClick={() => setShowAll((value) => !value)}
                  className="w-full border-t border-line px-4 py-2.5 text-left text-[12px] font-medium text-accent-ink hover:bg-surface-2"
                >
                  {showAll ? "Show fewer changes" : `Show all ${changes.length} changes`}
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
