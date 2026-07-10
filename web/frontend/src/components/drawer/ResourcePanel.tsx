"use client";

import { Bot, Clock3, DatabaseZap, Search, Sparkles, Workflow } from "lucide-react";

import type { Turn } from "@/lib/conversation";
import type { WSEvent } from "@/lib/types";

const compactNumber = (value: number) => new Intl.NumberFormat("en", {
  notation: value >= 1000 ? "compact" : "standard",
  maximumFractionDigits: 1,
}).format(value);

const durationLabel = (seconds: number) => seconds >= 60
  ? `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  : `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;

function recordOf(event: WSEvent): Record<string, unknown> {
  return event.type === "trajectory"
    ? (event.data ?? {}) as Record<string, unknown>
    : event as Record<string, unknown>;
}

function actionName(record: Record<string, unknown>): string {
  const action = record.action as Record<string, unknown> | undefined;
  return String(action?.name ?? "");
}

function eventToolCounts(events: WSEvent[]) {
  const counts: Record<string, number> = {};
  for (const event of events) {
    const record = recordOf(event);
    if (record.type !== "step") continue;
    const name = actionName(record);
    if (name) counts[name] = (counts[name] ?? 0) + 1;
  }
  return counts;
}

function agentDuration(events: WSEvent[]): number | null {
  const timestamps = events
    .map((event) => Date.parse(String(recordOf(event).timestamp ?? "")))
    .filter(Number.isFinite);
  if (timestamps.length < 2) return null;
  return Math.max(0, (Math.max(...timestamps) - Math.min(...timestamps)) / 1000);
}

export default function ResourcePanel({ turn }: { turn: Turn }) {
  const usage = turn.meta.tokenUsage;
  const derivedTools = eventToolCounts(turn.events);
  const tools = Object.keys(turn.meta.toolCounts ?? {}).length ? turn.meta.toolCounts! : derivedTools;
  const queryCount = turn.meta.totalQueries ?? tools.search ?? 0;
  const totalTokens = usage?.total_tokens ?? 0;
  const calls = usage?.llm_calls ?? 0;
  const elapsed = turn.meta.elapsed ?? 0;
  const byRole = Object.entries(usage?.by_role ?? {}).sort((a, b) => (
    (b[1].prompt_tokens + b[1].completion_tokens) - (a[1].prompt_tokens + a[1].completion_tokens)
  ));
  const phases = Object.entries(turn.meta.tokenPhases ?? {}).filter(([, value]) => value.total_tokens > 0);
  const agentRows = turn.workers.map((worker) => {
    const counts = eventToolCounts(worker.events);
    return {
      name: worker.name,
      status: worker.status,
      steps: Object.values(counts).reduce((sum, count) => sum + count, 0),
      searches: counts.search ?? 0,
      opens: counts.open ?? 0,
      finds: counts.find ?? 0,
      duration: agentDuration(worker.events),
    };
  });

  return (
    <div className="min-w-0">
      <div className="grid grid-cols-2 border-b border-line sm:grid-cols-4">
        {[
          { label: "Tokens", value: totalTokens ? compactNumber(totalTokens) : "--", icon: Sparkles },
          { label: "LLM calls", value: calls ? compactNumber(calls) : "--", icon: Bot },
          { label: "Searches", value: compactNumber(queryCount), icon: Search },
          { label: "Elapsed", value: elapsed ? durationLabel(elapsed) : "--", icon: Clock3 },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="border-b border-line px-4 py-3 odd:border-r sm:border-b-0 sm:border-r sm:last:border-r-0">
            <Icon className="mb-2 text-accent-ink" size={15} />
            <div className="text-[17px] font-semibold tabular-nums text-ink">{value}</div>
            <div className="mt-0.5 text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {usage && (
        <div className="border-b border-line px-4 py-3 text-[11px] text-ink-dim">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>Prompt <b className="font-medium text-ink">{compactNumber(usage.prompt_tokens)}</b></span>
            <span>Completion <b className="font-medium text-ink">{compactNumber(usage.completion_tokens)}</b></span>
            <span>Cached <b className="font-medium text-ink">{compactNumber(usage.cached_prompt_tokens ?? 0)}</b></span>
            {typeof usage.cache_hit_rate === "number" && (
              <span>Cache hit <b className="font-medium text-ink">{Math.round(usage.cache_hit_rate * 100)}%</b></span>
            )}
          </div>
        </div>
      )}

      <section className="border-b border-line" aria-labelledby="model-usage-title">
        <div className="flex items-center gap-2 px-4 pb-2 pt-4">
          <DatabaseZap className="text-accent-ink" size={14} />
          <h3 id="model-usage-title" className="text-[12px] font-semibold uppercase tracking-wider text-ink-dim">Model usage</h3>
        </div>
        {byRole.length ? (
          <div className="divide-y divide-line">
            {byRole.map(([role, roleUsage]) => {
              const roleTokens = roleUsage.prompt_tokens + roleUsage.completion_tokens;
              const model = turn.meta.modelDistribution?.[role];
              const width = totalTokens ? Math.max(3, (roleTokens / totalTokens) * 100) : 0;
              return (
                <div key={role} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-3 text-[12px]">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-ink">{role.replaceAll("_", " ")}</div>
                      <div className="truncate text-[10px] text-ink-faint" title={model?.model}>{model?.model || "Model metadata unavailable"}</div>
                    </div>
                    <div className="shrink-0 text-right tabular-nums text-ink-dim">
                      <div>{compactNumber(roleTokens)} tokens</div>
                      <div className="text-[10px] text-ink-faint">{roleUsage.llm_calls} calls</div>
                    </div>
                  </div>
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${width}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="px-4 pb-4 text-[12px] text-ink-faint">
            {turn.status === "running" ? "Token totals appear when the run completes" : "No token telemetry recorded for this run"}
          </div>
        )}
      </section>

      {phases.length > 0 && (
        <section className="border-b border-line px-4 py-4" aria-labelledby="phase-usage-title">
          <div className="mb-3 flex items-center gap-2">
            <Workflow className="text-accent-ink" size={14} />
            <h3 id="phase-usage-title" className="text-[12px] font-semibold uppercase tracking-wider text-ink-dim">Phases</h3>
          </div>
          <div className="space-y-2">
            {phases.map(([phase, value]) => (
              <div key={phase} className="flex items-center justify-between gap-3 text-[12px]">
                <span className="capitalize text-ink-dim">{phase.replaceAll("_", " ")}</span>
                <span className="tabular-nums text-ink">{compactNumber(value.total_tokens)} tokens · {value.llm_calls} calls</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section aria-labelledby="agent-resource-title">
        <div className="flex items-center gap-2 px-4 pb-2 pt-4">
          <Bot className="text-accent-ink" size={14} />
          <h3 id="agent-resource-title" className="text-[12px] font-semibold uppercase tracking-wider text-ink-dim">Agent activity</h3>
        </div>
        {agentRows.length ? (
          <div className="divide-y divide-line">
            {agentRows.map((agent) => (
              <div key={agent.name} className="flex items-center justify-between gap-4 px-4 py-2.5 text-[11px]">
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium text-ink">{agent.name.replaceAll("_", " ")}</div>
                  <div className="mt-0.5 text-ink-faint">{agent.status}{agent.duration != null ? ` · ${durationLabel(agent.duration)}` : ""}</div>
                </div>
                <div className="shrink-0 text-right tabular-nums text-ink-dim">
                  <div>{agent.searches} search · {agent.opens} open · {agent.finds} find</div>
                  <div className="text-[10px] text-ink-faint">{agent.steps} tool steps</div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-4 pb-4 text-[12px] text-ink-faint">No subagent activity recorded</div>
        )}
      </section>
    </div>
  );
}
