"use client";

import { useState, type ComponentType } from "react";
import {
  Users, LayoutGrid, BarChart3, FileCheck, Eye, Compass, Search, BookOpen, CheckCircle2,
  Loader2, Maximize2, MessageSquarePlus, TriangleAlert, Terminal, Sparkles,
} from "lucide-react";
import type { WSEvent } from "@/lib/types";
import { skillExecutionInfo } from "@/lib/runState";
import {
  clipLines,
  formatPreviewText,
  isCodeTool,
  parseExecArgs,
  summarizeExecResult,
} from "@/lib/execPreview";
import { highlightCode } from "@/lib/codeHighlight";
import { agentLabel } from "./trace";
import Answer from "../conversation/Answer";
import { getAgentReply } from "@/lib/api";
import ToolCallDetailDialog, { type ToolCallDetail } from "./ToolCallDetailDialog";

/* The orchestrator's own run trajectory: each step is a card — its reasoning
 * (thinking) on top, the action it took as a small coloured chip below. A
 * fan-out (consecutive dispatch events) collapses into ONE card listing every
 * sub-agent launched in that concurrent wave, by codename. */

type Icon = ComponentType<{ size?: number; className?: string }>;

interface DispatchAgent { name: string; task: string }
interface CheckAgent { name: string; status: string }

interface ActionView {
  icon: Icon;
  label: string;
  tone: string;
  detail?: string;
  agents?: DispatchAgent[];
  checks?: CheckAgent[];
  reports?: WorkerReport[];
  result?: string;
  spin?: boolean;
  toolCall?: ToolCallDetail;
}

const STR = (v: unknown) => (typeof v === "string" ? v : "");

function actionName(raw: unknown): string {
  if (raw && typeof raw === "object") return STR((raw as Record<string, unknown>).name);
  return STR(raw).match(/'name':\s*'([^']+)'/)?.[1] ?? "";
}
function actionArgs(raw: unknown): string {
  if (raw && typeof raw === "object") {
    const a = (raw as Record<string, unknown>).args;
    return typeof a === "string" ? a : JSON.stringify(a ?? "");
  }
  return STR(raw);
}
const trim = (t: string, n = 120) => (t.length > n ? t.slice(0, n) + "…" : t);

const CHIP = {
  accent: "bg-accent/12 text-accent-ink",
  clay: "bg-clay/70 text-accent-ink",
  ok: "bg-ok/15 text-ok",
  error: "bg-err/10 text-err",
  neutral: "bg-surface-2 text-ink-dim",
} as const;

const STATUS_DOT: Record<string, string> = {
  completed: "bg-ok", partial: "bg-ok", running: "bg-accent", error: "bg-err",
};

function stepBorder(action: ActionView | null): string {
  if (!action) return "border-line";
  if (action.spin) return "border-accent/50";
  if (action.tone === CHIP.error) return "border-err/50";
  if (action.tone === CHIP.ok) return "border-ok/40";
  return "border-line-strong";
}

function stepView(name: string, args: string): ActionView | null {
  switch (name) {
    case "create_schema": {
      const tbl = args.match(/"table_label"\s*:\s*"([^"]+)"/)?.[1];
      return { icon: LayoutGrid, tone: CHIP.clay, label: "Built coverage schema", detail: tbl };
    }
    case "evaluate_progress":
      return { icon: BarChart3, tone: CHIP.clay, label: "Evaluated coverage" };
    case "synthesize_answer":
      return { icon: FileCheck, tone: CHIP.ok, label: "Synthesized answer" };
    case "search_and_read":
    case "search":
      return { icon: Search, tone: CHIP.neutral, label: "Searched", detail: args.match(/'query':\s*'([^']*)'/)?.[1] };
    case "open":
      return { icon: BookOpen, tone: CHIP.neutral, label: "Read a page" };
    case "exec": {
      const summary = parseExecArgs(args);
      return { icon: Terminal, tone: CHIP.clay, label: "Exec", detail: summary.detail };
    }
    case "enqueue_tasks":
      return null;
    default:
      return name ? { icon: Compass, tone: CHIP.neutral, label: name } : null;
  }
}

interface WorkerReport {
  agent_id: string;
  status?: string;
  agent_report?: { text?: string };
  last_message?: string;
  result?: string;
  grounded_findings?: { id: string; source_urls: string[] }[];
}

interface Card { k: number; reasoning: string; action: ActionView | null; report?: WorkerReport; children?: Card[]; reply?: { agent: string; messageId: string; timestamp: string }; }

function DeliveredReport({ report }: { report: WorkerReport }) {
  const [open, setOpen] = useState(false);
  const body = STR(report.agent_report?.text).trim() || STR(report.last_message).trim() || STR(report.result).trim();
  const status = STR(report.status);
  const labels: Record<string, string> = { completed: "已完成", error: "失败", failed: "失败", cancelled: "已取消", partial: "部分完成", blocked: "受阻" };
  return <details className="min-w-0" onToggle={(e) => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer rounded text-[13px] font-medium text-accent-ink focus-visible:outline-accent">
      {agentLabel(STR(report.agent_id))} 的报告
      {status && <span className="ml-2 text-xs font-normal text-ink-dim">{labels[status] ?? status}</span>}
      {!open && body && <span className="mt-1 line-clamp-2 break-words text-xs font-normal text-ink-dim">{trim(body, 180)}</span>}
    </summary>
    {open && <div className="mt-2 space-y-2">
      {body && <Answer markdown={body} evidenceSources={Object.fromEntries(
        (report.grounded_findings ?? []).filter(f => f.source_urls?.length).map(f => [f.id, f.source_urls]),
      )} />}
      <details>
        <summary className="cursor-pointer text-xs text-ink-dim">查看原始报告</summary>
        <pre className="mt-1 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(report, null, 2)}</pre>
      </details>
    </div>}
  </details>;
}

function FinalReply({ card, sessionId }: { card: Card; sessionId?: string | null }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    if (!sessionId || !card.reply || content !== null || loading) return;
    setLoading(true);
    setError("");
    try {
      const reply = await getAgentReply(sessionId, card.reply.agent, card.reply.messageId, card.reply.timestamp);
      setContent(reply.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取失败");
    } finally { setLoading(false); }
  };
  return <details className="min-w-0 font-sans" onToggle={(event) => { if (event.currentTarget.open) void load(); }}>
    <summary className="cursor-pointer rounded text-[13px] font-medium text-accent-ink focus-visible:outline-accent">最终回复</summary>
    <div className="mt-2 overflow-x-auto">
      {loading ? <p>读取中…</p> : error ? <div><p>{error}</p><button type="button" onClick={() => void load()}>重试</button></div>
        : <Answer markdown={content ?? card.reasoning} />}
    </div>
  </details>;
}

function skillBatchSummary(children: Card[]): string {
  const failed = children.filter(child => child.action?.toolCall?.status === "error"
    || child.action?.toolCall?.status === "cancelled").length;
  const ok = children.length - failed;
  return `技能编排 · ${children.length} 个子步骤 · 成功 ${ok}${failed ? ` / 失败 ${failed}` : ""}`;
}

function ReasoningBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.split(/\r?\n/).length > 3 || text.length > 220;
  return (
    <div className="mb-2">
      <p className={`text-[13px] leading-relaxed text-ink-dim ${open ? "" : "line-clamp-3"}`}>{text}</p>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="mt-1 text-[11px] font-medium text-accent-ink hover:underline"
        >
          {open ? "收起思考" : "展开思考"}
        </button>
      )}
    </div>
  );
}

function ResultPreview({ text, compact = false }: { text: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const formatted = formatPreviewText(text);
  if (!formatted) return null;
  const collapsed = clipLines(formatted, compact ? 2 : 4, compact ? 480 : 900);
  const expanded = clipLines(formatted, compact ? 10 : 16, 6000);
  const needsMore = formatted !== collapsed;
  const needsDialog = formatted.split(/\r?\n/).length > 16 || formatted.length > 6000;
  return (
    <div className="trace-result mt-1.5">
      <pre className={`m-0 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink-dim ${open || !needsMore ? "" : "trace-fade"}`}>
        ⎿ {open ? expanded : collapsed}
      </pre>
      {needsMore && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="mt-1 text-[11px] font-medium text-accent-ink hover:underline"
        >
          {open ? (needsDialog ? "收起（全文见详情）" : "收起") : "展开"}
        </button>
      )}
    </div>
  );
}

function CodeSnippet({ code, commandLine }: { code: string; commandLine: string }) {
  const [open, setOpen] = useState(false);
  if (!code && !commandLine) return null;
  if (!code) {
    return (
      <div className="trace-code mt-2 px-2.5 py-1.5 font-mono text-[11px]">
        <span className="trace-tok-cmt">$ </span>
        <span className="trace-tok-fn">{commandLine}</span>
      </div>
    );
  }
  const collapsed = clipLines(code, 6, 2400);
  const expanded = clipLines(code, 20, 8000);
  const needsMore = code !== collapsed;
  return (
    <div className="trace-code mt-2">
      <pre className="m-0 overflow-x-auto whitespace-pre px-2.5 py-2 font-mono text-[11px] leading-relaxed">
        {highlightCode(open ? expanded : collapsed)}
      </pre>
      {needsMore && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="border-t border-line px-2.5 py-1 text-[11px] font-medium text-accent-ink hover:underline"
        >
          {open ? "收起代码" : "展开代码"}
        </button>
      )}
    </div>
  );
}

function ExecBody({ detail }: { detail: ToolCallDetail }) {
  const args = parseExecArgs(detail.arguments);
  const result = detail.output ? summarizeExecResult(detail.output) : null;
  return (
    <div>
      <CodeSnippet code={args.code} commandLine={args.commandLine} />
      {result && (
        <div className="mt-2 space-y-1">
          <div className={`font-mono text-[11px] ${result.failed ? "text-err" : "text-ink-dim"}`}>
            {result.metaLine}
          </div>
          {result.stdout && <ResultPreview text={result.stdout} />}
          {result.stderr && (
            <div className="rounded-md border border-warn/30 bg-warn/5 px-2 py-1">
              <div className="text-[10px] font-medium uppercase tracking-wider text-warn">stderr</div>
              <ResultPreview text={result.stderr} compact />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const RUNNING_LABEL: Record<string, string> = {
  check_agents: "Checking on sub-agents",
  evaluate_progress: "Evaluating coverage",
  synthesize_answer: "Synthesizing answer",
  create_schema: "Building coverage schema",
  enqueue_tasks: "Queueing tasks",
  exec: "Exec",
};

export function buildCards(
  events: WSEvent[],
  status: "idle" | "running" | "completed" | "error",
  priorEvents: WSEvent[],
  agentName = "orchestrator",
): Card[] {
  const out: Card[] = [];
  const pending: { id: string; index: unknown; tool: string; card: Card }[] = [];
  const calls = new Map<string, Card>();
  const executionParents = new Map<string, Card>();
  const children = new Map<string, { card: Card; parentCallId: string; parentExecutionId: string }>();
  const live = new Map<string, string>();
  let legacyWave: Card | null = null;
  const trackWorker = (event: WSEvent) => {
    if (event.type !== "trajectory") return;
    const d = (event.data ?? {}) as Record<string, unknown>;
    const agent = STR(d.agent), type = STR(d.type);
    if (!agent || agent === "orchestrator") return;
    if (type === "dispatch") live.set(agent, "running");
    if (type === "agent_final" || type === "agent_complete") live.set(agent, "completed");
    if (type === "agent_error" || type === "error") live.set(agent, "error");
  };
  priorEvents.forEach(trackWorker);
  const runningAgents = () => [...live].filter(([, s]) => s === "running")
    .map(([name, workerStatus]) => ({ name, status: workerStatus }));
  const finishPending = () => {
    for (const call of pending.splice(0)) {
      if (!call.card.action) continue;
      call.card.action = { ...call.card.action, icon: Compass, spin: false,
        label: `${call.tool} · 已结束，未收到结果`,
        toolCall: call.card.action.toolCall && { ...call.card.action.toolCall, status: undefined },
      };
    }
  };

  events.forEach((e, i) => {
    if (e.type !== "trajectory") return;
    const d = (e.data ?? {}) as Record<string, unknown>;
    const t = STR(d.type), agent = STR(d.agent);
    trackWorker(e);

    const skill = skillExecutionInfo(d);
    if (skill) {
      if (agent !== agentName) return;
      const previous = children.get(skill.executionId);
      if (previous && !previous.card.action?.spin && skill.status === "running") return;
      const card: Card = previous?.card ?? { k: i, reasoning: "", action: null };
      const running = skill.status === "running" && status === "running";
      card.action = {
        icon: running ? Loader2 : skill.status === "error" || skill.status === "cancelled" ? TriangleAlert : Sparkles,
        spin: running, tone: skill.status === "error" ? CHIP.error : CHIP.neutral,
        label: `技能 · ${skill.skill}`,
        detail: running ? "执行中" : skill.status === "cancelled" ? "已取消"
          : skill.status === "error" ? "执行失败" : skill.status === "running" ? "未收到结果" : "已完成",
        result: skill.output,
        toolCall: { tool: skill.skill, kind: "skill", executionId: skill.executionId,
          arguments: JSON.stringify({ argv: skill.argv }), output: skill.output, agent,
          timestamp: STR(d.timestamp), status: skill.status },
      };
      children.set(skill.executionId, { card, parentCallId: skill.parentCallId, parentExecutionId: skill.parentExecutionId });
      return;
    }
    if (agentName !== "orchestrator" && agent === agentName && t === "agent_final") {
      out.push({ k: i, reasoning: STR(d.reasoning), action: null,
        reply: { agent, messageId: STR(d.message_id), timestamp: STR(d.timestamp) } });
      return;
    }

    if (t === "task_complete" || t === "task_error") {
      finishPending();
      out.push({ k: i, reasoning: "", action: {
        icon: t === "task_complete" ? CheckCircle2 : TriangleAlert,
        tone: t === "task_complete" ? CHIP.ok : CHIP.error,
        label: t === "task_complete" ? "Finished & synthesized" : "运行未完成",
      } });
      return;
    }
    if (t === "dispatch" && agent && agentName === "orchestrator") {
      const owner = [...pending].reverse().find((p) => p.tool === "enqueue_tasks")?.card;
      const card = owner ?? legacyWave ?? { k: i, reasoning: "", action: {
        icon: Users, tone: CHIP.accent, label: "", agents: [],
      } };
      if (!owner && !legacyWave) { out.push(card); legacyWave = card; }
      if (card.action) {
        const agents = [...(card.action.agents ?? []), { name: agent, task: trim(STR(d.task)) }];
        card.action = { ...card.action, agents,
          label: owner ? `正在派发 ${agents.length} 个代理…`
            : agents.length > 1 ? `Dispatched ${agents.length} agents (concurrent)` : "Dispatched 1 agent",
        };
      }
      return;
    }
    if (t === "harness" && STR(d.kind) === "steer_injected") {
      legacyWave = null;
      out.push({ k: i, reasoning: "", action: {
        icon: MessageSquarePlus, tone: CHIP.accent,
        label: STR(d.mode) === "after_tool" ? "工具返回后已加入追问" : "已加入立即引导",
        detail: trim(STR(d.text), 140),
      } });
      return;
    }
    if (agent !== agentName) return;
    if (t === "agent_report" && agent === "orchestrator" && d.report && typeof d.report === "object") {
      legacyWave = null;
      out.push({ k: i, reasoning: "", action: null, report: d.report as WorkerReport });
      return;
    }
    if (t === "tool_call_started") {
      if (d.tool_call_id && calls.has(STR(d.tool_call_id))) return;
      legacyWave = null;
      const tool = STR(d.tool);
      const args = actionArgs({ args: d.args });
      const exec = tool === "exec" ? parseExecArgs(args) : null;
      const card: Card = { k: i, reasoning: STR(d.reasoning).trim(), action: {
        icon: Loader2, spin: true, tone: tool === "exec" ? CHIP.clay : CHIP.neutral,
        label: tool === "exec" ? "Exec…" : `${RUNNING_LABEL[tool] ?? tool}…`,
        detail: exec?.detail,
        toolCall: { tool, arguments: args, output: "", agent,
          timestamp: STR(d.timestamp), status: "running" },
      } };
      out.push(card);
      if (d.tool_call_id) calls.set(STR(d.tool_call_id), card);
      pending.push({ id: STR(d.tool_call_id), index: d.step_index, tool, card });
      return;
    }
    if (t !== "step" && t !== "tool_call_failed") return;
    const failed = t === "tool_call_failed" || d.status === "error";
    const name = t === "step" ? actionName(d.action) : STR(d.tool);
    const args = t === "step" ? actionArgs(d.action) : actionArgs({ args: d.args });
    const id = STR(d.tool_call_id);
    const match = pending.findIndex((call) => id ? call.id === id
      : d.step_index != null && call.index != null ? call.index === d.step_index : call.tool === name);
    const started = match >= 0 ? pending.splice(match, 1)[0].card : null;
    const card = started ?? calls.get(id) ?? (name === "enqueue_tasks" ? legacyWave : null)
      ?? { k: i, reasoning: "", action: null };
    if (!started && !calls.has(id) && card !== legacyWave) out.push(card);
    if (id) calls.set(id, card);
    const agents = card.action?.agents;
    const fullResult = STR(d.observation || d.observation_summary || d.error).trim();
    if (name === "exec") {
      try {
        const result = JSON.parse(fullResult);
        if (result.execution_id) executionParents.set(result.execution_id, card);
      } catch { /* 执行失败回执可能是纯文本。 */ }
    }
    let action: ActionView | null;
    if (failed) {
      action = { icon: TriangleAlert, tone: CHIP.error,
        label: name === "exec" ? `Exec · ${d.status === "cancelled" ? "已取消" : "失败"}`
          : `${name} · ${d.status === "cancelled" ? "已取消" : "调用失败"}`,
        detail: name === "exec" ? parseExecArgs(args).detail : undefined };
    } else if (name === "enqueue_tasks") {
      action = { icon: Users, tone: CHIP.accent, agents,
        label: agents?.length ? agents.length > 1 ? `Dispatched ${agents.length} agents (concurrent)`
          : "Dispatched 1 agent" : "Tasks queued" };
    } else if (name === "check_agents") {
      let checks = runningAgents();
      let reports: WorkerReport[] = [];
      let label = checks.length ? `Checked ${checks.length} in-flight agents` : "Checked on sub-agents";
      try {
        const receipt = JSON.parse(fullResult);
        if (receipt.await_reports === true) label = "等待下一份 Agent 报告";
        if (receipt.await_reports === false) label = "没有待接收的 Agent 报告";
        if (Array.isArray(receipt.reports)) {
          reports = receipt.reports.filter((r: WorkerReport) => r && typeof r.agent_id === "string");
          if (Array.isArray(receipt.running_ids)) {
            checks = receipt.running_ids.map((name: string) => ({ name, status: "running" }));
          }
          if (reports.length) label = `收到 ${reports.length} 份 Agent 报告`;
          else if (receipt.interrupted_by === "user_follow_up") label = "用户追问已打断等待";
          else if (receipt.timed_out) label = "等待报告超时";
          else label = checks.length ? "暂未收到 Agent 报告" : "没有待接收的 Agent 报告";
        }
      } catch { /* 旧版工具回执可能只保留了文本摘要。 */ }
      action = { icon: Eye, tone: CHIP.neutral, checks, reports, label };
    } else action = stepView(name, args);
    if (action) {
      const hideResult = (name === "enqueue_tasks" && agents?.length && !failed) || action.reports?.length
        || name === "exec";
      action.result = hideResult ? undefined : fullResult;
      action.toolCall = { tool: name, arguments: args, output: fullResult, agent,
        timestamp: card.action?.toolCall?.timestamp || STR(d.timestamp),
        status: failed ? d.status === "cancelled" ? "cancelled" : "error" : "completed" };
      if (name === "exec" && !action.detail) action.detail = parseExecArgs(args).detail;
    }
    card.reasoning = STR(d.reasoning).trim() || card.reasoning;
    card.action = action;
    legacyWave = null;
  });
  if (status === "completed" || status === "error") finishPending();
  else for (const call of pending) {
    if (call.tool === "check_agents" && call.card.action) call.card.action.checks = runningAgents();
  }
  const orphans = new Map<string, Card>();
  for (const child of children.values()) {
    let parent = calls.get(child.parentCallId) ?? executionParents.get(child.parentExecutionId)
      ?? orphans.get(child.parentExecutionId);
    if (!parent) {
      parent = { k: -child.card.k - 1, reasoning: "", action: {
        icon: Terminal, tone: CHIP.clay, label: "Exec", detail: "父调用记录未载入",
      } };
      orphans.set(child.parentExecutionId, parent);
      out.push(parent);
    }
    (parent.children ??= []).push(child.card);
  }
  return out;
}

export default function OrchestratorTimeline({ events, status = "running", priorEvents = [], agentName = "orchestrator", sessionId }: {
  events: WSEvent[];
  status?: "idle" | "running" | "completed" | "error";
  priorEvents?: WSEvent[];
  agentName?: string;
  sessionId?: string | null;
}) {
  const cards = buildCards(events, status, priorEvents, agentName);
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const selectedTool = cards.flatMap(card => [card, ...(card.children ?? [])])
    .find((card) => card.k === selectedKey)?.action?.toolCall ?? null;
  if (cards.length === 0) {
    return <div className="px-4 py-3 text-[12.5px] text-ink-faint">Orchestrator is starting…</div>;
  }
  return (
    <div className="space-y-2 px-4 py-3">
      {cards.map((c) => (
        <div key={c.k} className={`trace-step rise-in surface rounded-xl border-l-2 px-3.5 py-2.5 ${stepBorder(c.action)}`}>
          {c.report && <DeliveredReport report={c.report} />}
          {c.reasoning && (c.action ? <ReasoningBlock text={c.reasoning} /> : (
            <FinalReply card={c} sessionId={sessionId} />
          ))}
          {c.action && (
            <StepAction action={c.action} onOpenTool={() => setSelectedKey(c.k)} />
          )}
          {c.action?.reports?.map((report, i) => (
            <div className="mt-2" key={i}><DeliveredReport report={report} /></div>
          ))}
          {!!c.children?.length && (
            <details className="trace-term mt-2">
              <summary className="cursor-pointer rounded px-1 text-xs text-ink-dim focus-visible:outline-accent">
                {skillBatchSummary(c.children)}
              </summary>
              <div className="mt-1.5 space-y-1.5 border-l border-accent/30 pl-3">
                {c.children.map(child => child.action && (
                  <StepAction key={child.k} action={child.action} onOpenTool={() => setSelectedKey(child.k)} compact />
                ))}
              </div>
            </details>
          )}
        </div>
      ))}
      <ToolCallDetailDialog key={selectedKey} detail={selectedTool} sessionId={sessionId} onClose={() => setSelectedKey(null)} />
    </div>
  );
}

function StepAction({
  action,
  onOpenTool,
  compact = false,
}: {
  action: ActionView;
  onOpenTool: () => void;
  compact?: boolean;
}) {
  const shell = `rounded-lg px-3 py-2 ${action.tone}`;
  const header = (
    <div className={`flex items-center gap-1.5 ${compact ? "text-xs" : "text-[12.5px] font-medium"}`}>
      <action.icon size={compact ? 12 : 13} className={action.spin ? "animate-spin" : undefined} />
      <span>{action.label}</span>
      {action.detail && (
        <span className={`truncate font-normal text-ink-dim ${compact ? "ml-auto text-[10px]" : "opacity-90"}`}>
          {compact ? action.detail : `· ${action.detail}`}
        </span>
      )}
      {action.toolCall && <Maximize2 className={`${compact ? "" : "ml-auto"} shrink-0 opacity-60`} size={compact ? 11 : 12} />}
    </div>
  );

  return (
    <div className={shell}>
      {action.toolCall ? (
        <button
          type="button"
          onClick={onOpenTool}
          aria-label={`View full parameters and output for ${action.toolCall.tool}`}
          className="w-full rounded-md text-left transition-[filter] hover:brightness-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          {header}
        </button>
      ) : header}

      {action.toolCall && isCodeTool(action.toolCall) ? (
        <ExecBody detail={action.toolCall} />
      ) : action.result ? (
        <ResultPreview text={action.result} compact={compact} />
      ) : null}

      {action.agents && action.agents.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {action.agents.map((a, ai) => (
            <li key={ai} className="flex gap-2 text-[11.5px] font-normal leading-snug">
              <span className="shrink-0 font-mono font-medium text-accent-ink">{agentLabel(a.name)}</span>
              <span className="line-clamp-2 text-ink-dim">{a.task}</span>
            </li>
          ))}
        </ul>
      )}

      {action.checks && action.checks.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {action.checks.map((a, ai) => (
            <span key={ai} className="flex items-center gap-1.5 rounded-md bg-paper px-2 py-1 font-mono text-[11px] text-ink-dim">
              <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[a.status] ?? "bg-ink-faint"}`} />
              {agentLabel(a.name)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
