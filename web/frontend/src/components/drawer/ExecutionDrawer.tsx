"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X, Maximize2, Minimize2, Table2, FileText, FolderTree, Activity, Info } from "lucide-react";
import AgentWall from "@/components/workbench/AgentWall";
import TraceDrawer from "@/components/workbench/TraceDrawer";
import CoverageTable from "@/components/coverage/CoverageTable";
import EvidenceList from "@/components/evidence/EvidenceList";
import FileTree from "@/components/workspace/FileTree";
import FileViewer from "@/components/workspace/FileViewer";
import AsyncFeedback from "@/components/ui/AsyncFeedback";
import type { Turn } from "@/lib/conversation";
import type { FileNode } from "@/lib/types";

type Tab = "coverage" | "evidence" | "files" | "events";

interface Props {
  turn: Turn;
  sessionId: string | null;
  fileTree: FileNode[];
  selectedFile: string | null;
  onSelectFile: (path: string | null) => void;
  fileStatus: "idle" | "loading" | "ready" | "error";
  fileError?: string | null;
  onRetryFiles: () => void;
  onClose: () => void;
}

const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  { id: "coverage", label: "Coverage", icon: <Table2 size={13} /> },
  { id: "evidence", label: "Evidence", icon: <FileText size={13} /> },
  { id: "files", label: "Files", icon: <FolderTree size={13} /> },
  { id: "events", label: "Events", icon: <Activity size={13} /> },
];

export default function ExecutionDrawer({
  turn,
  sessionId,
  fileTree,
  selectedFile,
  onSelectFile,
  fileStatus,
  fileError = null,
  onRetryFiles,
  onClose,
}: Props) {
  const [tab, setTab] = useState<Tab>("coverage");
  const [traceAgent, setTraceAgent] = useState<string | null>(null);
  const [max, setMax] = useState(false);

  // Esc restores the maximized drawer; when a trace is open, Esc closes it first.
  useEffect(() => {
    if (!max || traceAgent) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMax(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [max, traceAgent]);

  const state = turn.searchState;
  const historicalStateUnavailable = turn.stateSource === "unavailable";
  const stateLabel = turn.stateSource === "snapshot"
    ? "Turn snapshot"
    : turn.stateSource === "latest"
      ? "Latest session state"
      : turn.stateSource === "unavailable"
        ? "Snapshot unavailable"
        : null;
  const activeWorker = turn.workers.find((w) => w.name === traceAgent) ?? null;
  const running = turn.workers.filter((w) => w.status === "running").length;

  const body = (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      {/* header */}
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <span className="font-serif text-[16px] font-semibold text-ink">Activity</span>
        {stateLabel && (
          <span className="flex items-center gap-1 text-[11px] text-ink-faint">
            <Info size={12} />
            {stateLabel}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setMax((v) => !v)} title={max ? "Restore" : "Maximize"}
            className="hidden rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink min-[1180px]:inline-flex">
            {max ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <button onClick={onClose} title="Close"
            className="rounded-lg p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink">
            <X size={17} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* sub-agents */}
        <div className="border-b border-line">
          <div className="px-4 pt-3 text-[11px] uppercase tracking-wider text-ink-faint">
            Subagents · {turn.workers.length}{running > 0 && ` · ${running} active`}
          </div>
          <AgentWall workers={turn.workers} onSelect={setTraceAgent} />
        </div>

        {/* tabs */}
        <div className="sticky top-0 z-10 flex gap-1 overflow-x-auto border-b border-line bg-surface px-1 sm:px-3">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-2.5 py-2.5 text-[13px] transition-colors sm:px-3 ${
                tab === t.id ? "border-accent font-medium text-ink" : "border-transparent text-ink-dim hover:text-ink"
              }`}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-1">
          {tab === "coverage" && (
            historicalStateUnavailable ? (
              <HistoricalStateNotice kind="Coverage" />
            ) : (
              <CoverageTable
                coverageMap={state?.coverage_map ?? null}
                evidence={state?.evidence_graph?.nodes ?? []}
              />
            )
          )}
          {tab === "evidence" && (
            historicalStateUnavailable
              ? <HistoricalStateNotice kind="Evidence" />
              : <EvidenceList nodes={state?.evidence_graph?.nodes ?? []} />
          )}
          {tab === "files" &&
            (selectedFile && sessionId ? (
              <FileViewer key={`${sessionId}:${selectedFile}`} sessionId={sessionId} filePath={selectedFile} onClose={() => onSelectFile(null)} />
            ) : fileTree.length > 0 ? (
              <FileTree tree={fileTree} onFileSelect={onSelectFile} selectedFile={selectedFile} />
            ) : fileStatus === "error" ? (
              <AsyncFeedback status="error" message="Couldn’t load workspace files" detail={`${fileError ?? "The workspace is unavailable"}. Try again after checking the backend.`} onRetry={onRetryFiles} />
            ) : fileStatus === "loading" ? (
              <AsyncFeedback status="loading" message="Loading workspace files…" />
            ) : (
              <div className="p-4 text-[13px] text-ink-faint">{sessionId ? "No files in this workspace" : "No workspace yet"}</div>
            ))}
          {tab === "events" && <EventsLog events={turn.events} />}
        </div>
      </div>

      <TraceDrawer worker={activeWorker} onClose={() => setTraceAgent(null)} />
    </div>
  );

  if (max) {
    return createPortal(
      <div className="fade-in fixed inset-0 z-[60] bg-paper p-3">
        <div className="surface h-full w-full overflow-hidden rounded-xl shadow-2xl">{body}</div>
      </div>,
      document.body,
    );
  }

  return <div className="drawer-in h-full">{body}</div>;
}

function HistoricalStateNotice({ kind }: { kind: "Coverage" | "Evidence" }) {
  return (
    <div role="note" className="flex items-start gap-2.5 p-4 text-[13px] text-ink-dim">
      <Info className="mt-0.5 shrink-0 text-accent-ink" size={16} />
      <div>
        <p className="font-medium text-ink">{kind} snapshot unavailable for this turn</p>
        <p className="mt-1 max-w-md text-[12px] leading-5 text-ink-faint">
          This conversation predates per-turn snapshots. Its latest session state remains available on the final turn.
        </p>
      </div>
    </div>
  );
}

function EventsLog({ events }: { events: { type: string; data?: unknown }[] }) {
  if (events.length === 0) return <div className="p-4 text-[13px] text-ink-faint">No events</div>;
  return (
    <div className="space-y-1 p-3 font-mono text-[12px]">
      {events.map((e, i) => (
        <div key={i} className="text-ink-dim">
          <span className="text-ink-faint">{String(i).padStart(3, "0")}</span>{" "}
          <span className="text-accent-ink">{e.type}</span>{" "}
          {e.data ? JSON.stringify(e.data).slice(0, 120) : ""}
        </div>
      ))}
    </div>
  );
}
