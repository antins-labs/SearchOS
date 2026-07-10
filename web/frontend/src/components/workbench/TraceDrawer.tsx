"use client";

import { useEffect, useState } from "react";
import { X, Loader2, CheckCircle2, XCircle, Circle } from "lucide-react";
import type { AgentCardData } from "./AgentCard";
import { TraceLine, agentLabel } from "./trace";
import ToolCallDetailDialog, { type ToolCallDetail } from "./ToolCallDetailDialog";

const STATUS = {
  pending: { icon: <Circle size={13} className="text-ink-faint" />, label: "pending" },
  running: { icon: <Loader2 size={13} className="animate-spin text-accent dark:text-accent" />, label: "running" },
  completed: { icon: <CheckCircle2 size={13} className="text-ok dark:text-ok" />, label: "done" },
  error: { icon: <XCircle size={13} className="text-err dark:text-err" />, label: "error" },
} as const;

/** Slide-over showing the full step-by-step trace of one sub-agent. */
export default function TraceDrawer({
  worker,
  onClose,
}: {
  worker: AgentCardData | null;
  onClose: () => void;
}) {
  const [selectedTool, setSelectedTool] = useState<ToolCallDetail | null>(null);
  const open = worker != null;
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!worker) return null;
  const s = STATUS[worker.status];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="overlay-in absolute inset-0 bg-black/40 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="surface drawer-in relative flex h-full w-[min(560px,92vw)] flex-col rounded-l-xl shadow-2xl">
        {/* header */}
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          {s.icon}
          <span className="text-sm font-semibold text-ink">
            {agentLabel(worker.name)}
          </span>
          <span className="font-mono text-[10px] text-ink-faint">{worker.name}</span>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] capitalize text-ink-dim">
            {s.label}
          </span>
          {worker.scope && (
            <span className="truncate text-xs text-ink-faint">{worker.scope}</span>
          )}
          <button
            onClick={onClose}
            aria-label="Close trace"
            className="ml-auto rounded p-1 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        {/* trace body */}
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-4 py-3 font-mono text-xs">
          {worker.events.length === 0 ? (
            <div className="text-ink-faint">No trace recorded yet.</div>
          ) : (
            worker.events.map((e, i) => (
              <TraceLine key={i} event={e} onOpenTool={setSelectedTool} />
            ))
          )}
          {worker.status === "running" && (
            <div className="flex items-center gap-1.5 pt-1 text-accent dark:text-accent">
              <Loader2 size={11} className="animate-spin" /> live…
            </div>
          )}
        </div>
      </aside>
      <ToolCallDetailDialog detail={selectedTool} onClose={() => setSelectedTool(null)} />
    </div>
  );
}
