"use client";

import { useRef, useEffect } from "react";
import type { WSEvent, EvidenceNode } from "@/lib/types";
import { Search, FileText, AlertCircle, CheckCircle2, Zap, Compass, LayoutGrid, BarChart3, FileCheck } from "lucide-react";

interface Props {
  query: string | null;
  events: WSEvent[];
  status: "idle" | "running" | "completed" | "error";
  error: string | null;
}

export default function ChatPanel({ query, events, status, error }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length, status]);

  return (
    <div className="flex h-full flex-col overflow-y-auto px-4 py-4 space-y-3">
      {/* User query */}
      {query && (
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gray-100 px-4 py-2.5 text-gray-800 dark:bg-zinc-800 dark:text-zinc-200">
            {query}
          </div>
        </div>
      )}

      {/* Events */}
      {events.map((event, i) => (
        <EventBubble key={i} event={event} />
      ))}

      {/* Status */}
      {status === "running" && (
        <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-zinc-500">
          <div className="h-2 w-2 animate-pulse rounded-full bg-blue-500" />
          Searching...
        </div>
      )}
      {status === "completed" && (
        <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-500">
          <CheckCircle2 size={14} /> Search complete
        </div>
      )}
      {status === "error" && (
        <div className="flex items-center gap-2 text-sm text-red-500 dark:text-red-400">
          <AlertCircle size={14} /> {error || "Search failed"}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}

function EventBubble({ event }: { event: WSEvent }) {
  if (event.type === "trajectory") {
    const data = event.data as Record<string, unknown>;
    const rawAction = data?.action;
    const action = typeof rawAction === "object" && rawAction !== null
      ? String((rawAction as Record<string, unknown>).name || "")
      : String(rawAction || data?.type || "");
    const rawInput = typeof rawAction === "object" && rawAction !== null
      ? String((rawAction as Record<string, unknown>).args || "").slice(0, 120)
      : String(data?.action_input_summary || "").slice(0, 120);
    const obs = String(data?.observation || data?.observation_summary || "").slice(0, 200);

    // Skill injection
    if (data?.type === "skill_injection") {
      const skills = (data.skills as string[]) || [];
      return (
        <div className="flex items-center gap-2 rounded-md border border-amber-300/40 bg-amber-50/50 px-3 py-1.5 text-xs text-amber-600/80 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-400/80">
          <Zap size={12} className="shrink-0" />
          <span>Skill: {skills.join(", ")}</span>
        </div>
      );
    }

    // Orchestrator tool calls (warmup, schema, evaluate, synthesize)
    if (data?.type === "orchestrator_tool") {
      const tool = String(data.tool || "");
      const args = data.args as Record<string, unknown> | undefined;
      const result = String(data.result_preview || "").slice(0, 150);

      const toolConfig: Record<string, { icon: React.ReactNode; label: string; style: string }> = {
        search_and_read: { icon: <Compass size={12} />, label: "Warmup", style: "border-blue-300/40 bg-blue-50/30 text-blue-600/80 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-400/80" },
        create_schema: { icon: <LayoutGrid size={12} />, label: "Schema", style: "border-violet-300/40 bg-violet-50/30 text-violet-600/80 dark:border-violet-900/40 dark:bg-violet-950/20 dark:text-violet-400/80" },
        evaluate_progress: { icon: <BarChart3 size={12} />, label: "Evaluate", style: "border-blue-300/40 bg-blue-50/30 text-blue-600/80 dark:border-blue-900/40 dark:bg-blue-950/20 dark:text-blue-400/80" },
        synthesize_answer: { icon: <FileCheck size={12} />, label: "Synthesize", style: "border-green-300/40 bg-green-50/30 text-green-600/80 dark:border-green-900/40 dark:bg-green-950/20 dark:text-green-400/80" },
      };
      const cfg = toolConfig[tool] || { icon: <Search size={12} />, label: tool, style: "border-gray-300/40 bg-gray-50/30 text-gray-600/80 dark:border-gray-800/40 dark:bg-gray-950/20 dark:text-gray-400/80" };
      const detail = tool === "search_and_read" ? String(args?.query || "").slice(0, 80)
        : tool === "create_schema" ? result
        : result;

      return (
        <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${cfg.style}`}>
          <span className="mt-0.5 shrink-0">{cfg.icon}</span>
          <div className="min-w-0">
            <span className="font-medium">{cfg.label}</span>
            {detail && <p className="mt-0.5 text-[11px] opacity-70 line-clamp-2">{detail}</p>}
          </div>
        </div>
      );
    }

    // Tool calls
    if (action && data?.type === "step") {
      const isSearch = ["web_search", "search", "search_and_read"].includes(action);
      const isState = ["add_evidence", "mark_coverage", "update_frontier", "log_strategy", "batch_record", "add_entity", "add_dag_node"].includes(action);

      // Skip rendering state tools -- they show up as evidence/coverage events
      if (isState) return null;

      return (
        <div className="rounded-md border border-gray-200/60 bg-gray-50/40 px-3 py-2 dark:border-zinc-800/60 dark:bg-zinc-900/40">
          <div className="flex items-center gap-2 text-xs">
            <Search size={12} className={isSearch ? "text-blue-500/70 dark:text-blue-400/70" : "text-gray-400 dark:text-zinc-600"} />
            <span className="font-mono text-gray-500 dark:text-zinc-500">{action}</span>
            {rawInput && <span className="truncate text-gray-400 dark:text-zinc-600">{rawInput}</span>}
          </div>
          {obs && isSearch && (
            <p className="mt-1 text-xs text-gray-400 dark:text-zinc-600 line-clamp-1 pl-5">{obs}</p>
          )}
        </div>
      );
    }

    return null;
  }

  if (event.type === "evidence_added") {
    const node = event.node as EvidenceNode;
    const confPct = ((node?.confidence ?? 0) * 100).toFixed(0);
    const align = node?.alignment;
    const alignClass =
      align === "full"
        ? "text-emerald-700 dark:text-emerald-400"
        : align === "partial"
          ? "text-amber-700 dark:text-amber-400"
          : "text-gray-500 dark:text-zinc-500";
    return (
      <div className="rounded-lg border border-emerald-300/30 bg-emerald-50/20 p-3 dark:border-emerald-900/30 dark:bg-emerald-950/10">
        <div className="flex items-start gap-2.5">
          <div className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500 dark:bg-emerald-400" />
          <div className="min-w-0 flex-1">
            <p className="text-sm leading-relaxed text-gray-700 dark:text-zinc-300">{(node?.claim ?? "").slice(0, 120)}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-400 dark:text-zinc-600">
              {node?.table_id && (
                <span className="rounded border border-blue-300/60 px-1.5 py-0.5 font-mono text-blue-700 dark:border-blue-900/60 dark:text-blue-400">
                  {node.table_id}
                </span>
              )}
              {node?.entity && (
                <span className="text-gray-500 dark:text-zinc-500">{node.entity}.{node.attribute}</span>
              )}
              {align && (
                <span className={alignClass} title={node?.alignment_note || undefined}>{align}</span>
              )}
              <span>{confPct}%</span>
              {node?.source && (
                <a href={node.source} target="_blank" rel="noopener"
                   className="truncate text-gray-500 hover:text-gray-700 dark:text-zinc-500 dark:hover:text-zinc-400">
                  {node.source.slice(0, 50)}
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (event.type === "coverage_updated") {
    const cov = Number(event.coverage ?? 0);
    return (
      <div className="text-sm text-gray-500 dark:text-zinc-500">
        Coverage: {(cov * 100).toFixed(0)}% ({String(event.filled ?? 0)}/{String(event.total ?? 0)})
      </div>
    );
  }

  if (event.type === "search_complete") {
    const cov = Number(event.coverage ?? 0);
    const verdict = String(event.eval_verdict ?? "");
    const elapsed = Number(event.elapsed_s ?? 0);
    const tu = (event as Record<string, unknown>).token_usage as Record<string, number> | undefined;
    const tokenText = tu ? ` | ${(tu.total_tokens / 1000).toFixed(0)}K tokens (${tu.llm_calls} calls)` : "";
    return (
      <div className="rounded-lg border border-green-300 bg-green-50/30 p-3 text-sm text-green-700 dark:border-green-900 dark:bg-green-950/30 dark:text-green-400">
        <CheckCircle2 size={14} className="inline mr-1" />
        Complete -- {verdict} | Coverage: {(cov * 100).toFixed(0)}% | {elapsed.toFixed(1)}s{tokenText}
      </div>
    );
  }

  // Blackboard events
  if (event.type?.startsWith("blackboard.")) {
    const data = event.data as Record<string, unknown>;
    const agent = String(data?.agent || "");
    const content = String(data?.content || data?.type || "");
    return (
      <div className="text-xs text-gray-400 dark:text-zinc-600">
        [{agent}] {content.slice(0, 100)}
      </div>
    );
  }

  return null;
}
