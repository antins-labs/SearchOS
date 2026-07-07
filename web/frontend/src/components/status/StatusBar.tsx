"use client";

import type { SearchState } from "@/lib/types";

interface Props {
  state: SearchState | null;
  status: "idle" | "running" | "completed" | "error";
  elapsed: number;
  verdict: string | null;
}

export default function StatusBar({ state, status, elapsed, verdict }: Props) {
  const budget = state?.budget;
  const coverage = state?.coverage_map;
  const evidenceCount = state?.evidence_graph?.nodes?.length || 0;

  const budgetPct = budget ? (budget.consumed_queries / Math.max(budget.max_queries, 1)) * 100 : 0;
  const filled = coverage
    ? Object.values(coverage.cells).filter((c) => c.status === "filled").length
    : 0;
  const total = coverage ? Object.keys(coverage.cells).length : 0;
  const covPct = total > 0 ? (filled / total) * 100 : 0;

  const verdictColors: Record<string, string> = {
    PASS: "bg-gray-200 text-ink dark:bg-zinc-700 dark:text-zinc-300",
    BACKFILL: "bg-gray-200 text-accent-ink dark:bg-zinc-700 dark:text-accent",
    STRATEGY_SWITCH: "bg-gray-200 text-err dark:bg-zinc-700 dark:text-err",
  };

  const statusDot = {
    idle: "bg-line-strong dark:bg-zinc-600",
    running: "bg-blue-500 animate-pulse",
    completed: "bg-green-500",
    error: "bg-err",
  }[status];

  return (
    <div className="flex items-center gap-4 border-t border-line bg-gray-50 px-4 py-2 text-xs dark:border-zinc-800 dark:bg-zinc-900">
      {/* Status */}
      <div className="flex items-center gap-1.5">
        <div className={`h-2 w-2 rounded-full ${statusDot}`} />
        <span className="text-ink-dim capitalize dark:text-zinc-400">{status}</span>
      </div>

      {/* Coverage */}
      {total > 0 && (
        <div className="flex items-center gap-1.5">
          <span className="text-ink-dim dark:text-zinc-500">Coverage:</span>
          <div className="h-1.5 w-16 rounded-full bg-gray-200 dark:bg-zinc-800">
            <div
              className="h-1.5 rounded-full bg-gray-500 transition-all dark:bg-zinc-400"
              style={{ width: `${covPct}%` }}
            />
          </div>
          <span className="text-ink-dim dark:text-zinc-400">{covPct.toFixed(0)}%</span>
        </div>
      )}

      {/* Evidence */}
      <div className="text-ink-dim dark:text-zinc-500">
        Evidence: <span className="text-ink-dim dark:text-zinc-400">{evidenceCount}</span>
      </div>

      {/* Budget */}
      {budget && (
        <div className="flex items-center gap-1.5">
          <span className="text-ink-dim dark:text-zinc-500">Budget:</span>
          <div className="h-1.5 w-16 rounded-full bg-gray-200 dark:bg-zinc-800">
            <div
              className="h-1.5 rounded-full bg-blue-500 transition-all"
              style={{ width: `${Math.min(budgetPct, 100)}%` }}
            />
          </div>
          <span className="text-ink-dim dark:text-zinc-400">
            {budget.consumed_queries}/{budget.max_queries}
          </span>
        </div>
      )}

      {/* Verdict */}
      {verdict && (
        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${verdictColors[verdict] || "bg-gray-200 text-ink dark:bg-zinc-700 dark:text-zinc-300"}`}>
          {verdict}
        </span>
      )}

      {/* Timer */}
      <div className="ml-auto text-ink-faint dark:text-zinc-600">
        {elapsed > 0 ? `${elapsed.toFixed(1)}s` : ""}
      </div>
    </div>
  );
}
