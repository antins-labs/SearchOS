"use client";

import type { WSEvent } from "@/lib/types";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

interface Props {
  name: string;
  intent: string;
  scope: string;
  status: "pending" | "running" | "completed" | "error";
  events: WSEvent[];
}

export default function WorkerPane({ name, intent, scope, status, events }: Props) {
  const statusIcon = {
    pending: <Loader2 size={12} className="text-gray-400 dark:text-zinc-500" />,
    running: <Loader2 size={12} className="animate-spin text-blue-500 dark:text-blue-400" />,
    completed: <CheckCircle2 size={12} className="text-green-500 dark:text-green-400" />,
    error: <XCircle size={12} className="text-red-500 dark:text-red-400" />,
  }[status];

  return (
    <div className="flex h-full flex-col border border-gray-200 rounded-lg overflow-hidden bg-white dark:border-zinc-800 dark:bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-3 py-1.5 dark:border-zinc-800 dark:bg-zinc-900">
        {statusIcon}
        <span className="text-xs font-mono font-medium text-gray-700 dark:text-zinc-300">{name}</span>
        <span className="text-xs text-gray-400 dark:text-zinc-600">{intent}</span>
        <span className="ml-auto text-xs text-gray-300 truncate max-w-[100px] dark:text-zinc-700">{scope}</span>
      </div>

      {/* Terminal-like output */}
      <div className="flex-1 overflow-y-auto px-3 py-2 font-mono text-xs space-y-1">
        {events.map((e, i) => {
          if (e.type === "trajectory") {
            const d = e.data as Record<string, unknown>;
            const rawAct = d?.action;
            const action = typeof rawAct === "object" && rawAct !== null
              ? String((rawAct as Record<string, unknown>).name || "")
              : String(rawAct || "");
            const obs = String(d?.observation || d?.observation_summary || "").slice(0, 120);
            return (
              <div key={i}>
                <span className="text-blue-500 dark:text-blue-400">$ {action}</span>
                {obs && <div className="text-gray-400 dark:text-zinc-600 pl-2">{obs}</div>}
              </div>
            );
          }
          if (e.type === "evidence_added") {
            const node = (e as Record<string, unknown>).node as Record<string, unknown>;
            return (
              <div key={i} className="text-green-600 dark:text-green-400">
                + evidence: {String(node?.claim || "").slice(0, 80)}
              </div>
            );
          }
          return null;
        })}
        {status === "running" && events.length === 0 && (
          <div className="text-gray-300 dark:text-zinc-700">waiting...</div>
        )}
      </div>
    </div>
  );
}
