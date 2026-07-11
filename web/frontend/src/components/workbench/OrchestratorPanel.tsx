"use client";

import { useEffect, useRef, useState, type FormEvent, type ComponentType } from "react";
import {
  LayoutGrid,
  Users,
  BarChart3,
  FileCheck,
  ListTree,
  Compass,
  CheckCircle2,
  ChevronRight,
  ArrowUp,
} from "lucide-react";
import type { SearchState, WSEvent } from "@/lib/types";
import { agentLabel, agentNum } from "./trace";

export interface WorkerLite {
  name: string;
  status: "pending" | "running" | "completed" | "error";
}

interface Props {
  query: string | null;
  events: WSEvent[];
  searchState: SearchState | null;
  status: "idle" | "running" | "completed" | "error";
  workers: WorkerLite[];
  onSelectWorker: (name: string) => void;
  onSubmit: (q: string, opts: Record<string, never>) => void;
}

type Icon = ComponentType<{ size?: number; className?: string }>;
interface Msg {
  k: number;
  icon: Icon;
  cls: string;
  title: string;
  /** one-line summary shown while collapsed */
  preview?: string;
  /** expandable: dispatched agents */
  agents?: { name: string; task: string }[];
  /** expandable: labelled lists (schema rows/cols) */
  lists?: { label: string; items: string[] }[];
  /** expandable: a free-text body (agent answer) */
  text?: string;
}

interface Ctx {
  schema: string;
  covPct: number;
  entities: string[];
  attrs: string[];
}

const TOOL_META: Record<string, { label: string; icon: Icon; cls: string }> = {
  create_schema: { label: "Built coverage schema", icon: LayoutGrid, cls: "text-violet-500 dark:text-violet-400" },
  evaluate_progress: { label: "Evaluated coverage", icon: BarChart3, cls: "text-blue-500 dark:text-blue-400" },
  synthesize_answer: { label: "Synthesized answer", icon: FileCheck, cls: "text-emerald-500 dark:text-emerald-400" },
  search_and_read: { label: "Warmup exploration", icon: Compass, cls: "text-sky-500 dark:text-sky-400" },
};
const ACTION_META: Record<string, { label: string; icon: Icon; cls: string }> = {
  enqueue_tasks: { label: "Queued search tasks", icon: ListTree, cls: "text-violet-500 dark:text-violet-400" },
  check_agents: { label: "Checked on agents", icon: Users, cls: "text-blue-500 dark:text-blue-400" },
  create_schema: { label: "Built coverage schema", icon: LayoutGrid, cls: "text-violet-500 dark:text-violet-400" },
};

/** Ordered orchestrator feed. A fan-out wave (consecutive dispatch events)
 *  collapses into one bubble. Finishes key off `agent_final` only. */
function buildMessages(events: WSEvent[], ctx: Ctx): Msg[] {
  const out: Msg[] = [];
  let disp: { name: string; task: string }[] = [];
  let dispKey = -1;

  const flush = () => {
    if (!disp.length) return;
    out.push({
      k: dispKey,
      icon: Users,
      cls: "text-amber-500 dark:text-amber-400",
      title: disp.length === 1 ? `Dispatched ${agentLabel(disp[0].name)}` : `Dispatched ${disp.length} agents`,
      preview: disp.map((a) => agentLabel(a.name)).join(" · "),
      agents: disp,
    });
    disp = [];
  };

  events.forEach((e, i) => {
    if (e.type !== "trajectory") return;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = String(d.type || "");
    const agent = String(d.agent || "");

    if (t === "dispatch" && agent) {
      if (!disp.length) dispKey = i;
      disp.push({ name: agent, task: String(d.task || "") });
      return;
    }

    if (t === "orchestrator_tool") {
      const tool = String(d.tool || "");
      const m = TOOL_META[tool];
      if (!m) return;
      flush();
      const msg: Msg = { k: i, icon: m.icon, cls: m.cls, title: m.label };
      if (tool === "create_schema") {
        msg.preview = ctx.schema;
        const lists: { label: string; items: string[] }[] = [];
        if (ctx.entities.length) lists.push({ label: "Rows", items: ctx.entities });
        if (ctx.attrs.length) lists.push({ label: "Columns", items: ctx.attrs });
        if (lists.length) msg.lists = lists;
      } else if (tool === "evaluate_progress") {
        msg.preview = `coverage ${ctx.covPct}%`;
      } else if (tool === "synthesize_answer") {
        msg.preview = "final report ready";
      } else if (tool === "search_and_read") {
        msg.preview = "exploring the landscape";
      }
      out.push(msg);
    } else if (t === "step" && agent === "orchestrator") {
      const raw = d.action;
      const action = typeof raw === "string" ? raw.match(/'name':\s*'([^']+)'/)?.[1] : (raw as Record<string, unknown>)?.name;
      const m = action ? ACTION_META[String(action)] : undefined;
      if (!m) return;
      flush();
      const msg: Msg = { k: i, icon: m.icon, cls: m.cls, title: m.label };
      if (action === "enqueue_tasks") {
        const qm = String(d.observation || "").match(/"queued":\s*\[([^\]]*)\]/);
        const c = qm && qm[1].trim() ? qm[1].split(",").length : 0;
        msg.preview = c ? `${c} task${c > 1 ? "s" : ""} queued` : "no new tasks";
      } else if (action === "check_agents") {
        msg.preview = "watching sub-agents";
      }
      out.push(msg);
    } else if (t === "agent_final" && agent && agent !== "orchestrator") {
      flush();
      const r = String(d.reasoning || "").replace(/\s+/g, " ").trim();
      out.push({
        k: i,
        icon: CheckCircle2,
        cls: "text-emerald-500 dark:text-emerald-400",
        title: `${agentLabel(agent)} finished`,
        preview: r ? r.slice(0, 80) : undefined,
        text: r || undefined,
      });
    }
  });
  flush();
  return out;
}

const DOT: Record<string, string> = {
  running: "bg-amber-500 glow-pulse-amber",
  completed: "bg-emerald-500",
  error: "bg-red-500",
  pending: "bg-gray-300 dark:bg-zinc-700",
};

function rank(name: string): number {
  if (name.startsWith("explore") || name.startsWith("warmup")) return -1;
  if (name.startsWith("writer")) return 9999;
  return Number(agentNum(name)) || 0;
}

export default function OrchestratorPanel({
  query,
  events,
  searchState,
  status,
  workers,
  onSelectWorker,
  onSubmit,
}: Props) {
  const sortedWorkers = [...(workers ?? [])].sort((a, b) => rank(a.name) - rank(b.name));

  // context for feed bubbles — use the table that actually holds data
  const cm = searchState?.coverage_map;
  const cellKeys = Object.keys(cm?.cells ?? {});
  const tables = cm ? Object.values(cm.tables ?? {}) : [];
  const mainTbl =
    tables.slice().sort(
      (a, b) =>
        cellKeys.filter((k) => k.startsWith(`${b.table_id}/`)).length -
        cellKeys.filter((k) => k.startsWith(`${a.table_id}/`)).length,
    )[0] ?? null;
  const entities = mainTbl?.entities ?? [];
  const attrs = mainTbl?.attributes ?? [];
  const schemaSummary = entities.length || attrs.length ? `${entities.length} rows · ${attrs.length} cols` : "";
  const cellVals = Object.values(cm?.cells ?? {});
  const covPct = cellVals.length
    ? Math.round((cellVals.filter((c) => c.status === "filled").length / cellVals.length) * 100)
    : 0;

  const messages = buildMessages(events ?? [], { schema: schemaSummary, covPct, entities, attrs });

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, status]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* query header */}
      <div className="border-b border-black/5 px-4 py-3 dark:border-white/5">
        <div className="mb-1 flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-blue-600/70 dark:text-blue-400/70">
          <span className="text-blue-500 dark:text-blue-400">✻</span> Orchestrator
        </div>
        {query && <p className="text-sm leading-snug text-gray-700 dark:text-zinc-200">{query}</p>}
      </div>

      {/* live agent status grid */}
      {sortedWorkers.length > 0 && (
        <div className="border-b border-black/5 px-4 py-3 dark:border-white/5">
          <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-gray-400 dark:text-zinc-600">
            Agents · {sortedWorkers.length}
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(2.75rem,1fr))] gap-1.5">
            {sortedWorkers.map((w) => {
              const isExplore = w.name.startsWith("explore") || w.name.startsWith("warmup");
              return (
                <button
                  key={w.name}
                  onClick={() => onSelectWorker(w.name)}
                  title={`${agentLabel(w.name)} · ${w.status}`}
                  className="surface flex items-center justify-center gap-1 rounded-lg px-1.5 py-1.5 transition-all hover:-translate-y-0.5 hover:ring-1 hover:ring-amber-500/30"
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT[w.status] || DOT.pending}`} />
                  <span className="font-mono text-[11px] font-medium text-amber-600 dark:text-amber-400">
                    {isExplore ? "E" : agentNum(w.name) || "·"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* orchestrator feed */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <div className="pt-6 text-center text-xs text-gray-400 dark:text-zinc-600">
            {status === "running" ? "Orchestrator is starting…" : "No activity yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {messages.map((m) => (
              <FeedBubble key={m.k} msg={m} onSelectWorker={onSelectWorker} />
            ))}
            {status === "running" && (
              <div className="flex items-center gap-1.5 pl-7 pt-0.5 text-[11px] text-blue-500 dark:text-blue-400">
                <span className="glow-pulse h-1.5 w-1.5 rounded-full bg-blue-500" /> working…
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <Composer status={status} onSubmit={onSubmit} />
    </div>
  );
}

function FeedBubble({ msg, onSelectWorker }: { msg: Msg; onSelectWorker: (n: string) => void }) {
  const expandable = !!(msg.agents || msg.lists || msg.text);
  const [open, setOpen] = useState(false); // default closed — preview only

  return (
    <div className="rise-in flex gap-2">
      <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-black/5 dark:bg-white/5 ${msg.cls}`}>
        <msg.icon size={11} />
      </span>
      <div className="surface min-w-0 flex-1 rounded-xl rounded-tl-sm px-3 py-1.5">
        <button
          type="button"
          disabled={!expandable}
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center gap-1.5 text-left disabled:cursor-default"
        >
          <span className="text-xs font-medium text-gray-700 dark:text-zinc-200">{msg.title}</span>
          {expandable && (
            <ChevronRight
              size={12}
              className={`ml-auto shrink-0 text-gray-400 transition-transform dark:text-zinc-600 ${open ? "rotate-90" : ""}`}
            />
          )}
        </button>

        {/* collapsed: preview only */}
        {!open && msg.preview && (
          <p className="mt-0.5 line-clamp-1 text-[11px] text-gray-500 dark:text-zinc-500">{msg.preview}</p>
        )}

        {/* expanded content */}
        {open && expandable && (
          <div className="mt-1.5 space-y-1.5 border-t border-black/5 pt-1.5 dark:border-white/5">
            {msg.agents?.map((a) => (
              <button key={a.name} onClick={() => onSelectWorker(a.name)} className="block w-full text-left">
                <span className="font-mono text-[11px] font-medium text-amber-600 dark:text-amber-400">
                  {agentLabel(a.name)}
                </span>
                {a.task && (
                  <span className="line-clamp-2 text-[11px] text-gray-500 dark:text-zinc-500">{a.task}</span>
                )}
              </button>
            ))}
            {msg.lists?.map((l) => (
              <div key={l.label} className="text-[11px]">
                <span className="text-gray-400 dark:text-zinc-600">{l.label}: </span>
                <span className="text-gray-600 dark:text-zinc-300">{l.items.join(", ")}</span>
              </div>
            ))}
            {msg.text && (
              <p className="text-[11px] leading-relaxed text-gray-600 dark:text-zinc-400">{msg.text}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Composer({ status, onSubmit }: { status: Props["status"]; onSubmit: Props["onSubmit"] }) {
  const [text, setText] = useState("");
  const running = status === "running";

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || running) return;
    onSubmit(q, {});
    setText("");
  };

  return (
    <form onSubmit={submit} className="border-t border-black/5 p-3 dark:border-white/5">
      <div className="surface flex items-center gap-2 rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-blue-500/40">
        <span className="select-none text-gray-400 dark:text-zinc-600">&gt;</span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={running}
          placeholder={running ? "searching…" : "start a new search"}
          spellCheck={false}
          className="min-w-0 flex-1 bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-400 disabled:opacity-50 dark:text-zinc-100 dark:placeholder:text-zinc-600"
        />
        <button
          type="submit"
          disabled={running || !text.trim()}
          aria-label="Search"
          className="rounded-lg bg-blue-500/15 p-1.5 text-blue-600 transition-colors hover:bg-blue-500/25 disabled:opacity-30 dark:text-blue-400"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </form>
  );
}
