"use client";

import { useEffect, useState } from "react";
import { ArrowRight, Braces, Check, ChevronDown, Circle, CirclePause, Clock3, FileCode2, FlaskConical, GitBranch, Loader2, RefreshCw, Search, ShieldCheck, TriangleAlert } from "lucide-react";
import { getSkillCreationProgress, getSkillCreationRounds, type SkillCreationJob, type SkillCreationProgress as Progress, type SkillCreationRounds } from "@/lib/api";
import SkillUserAction from "./SkillUserAction";

const phases = [
  { id: "research", role: "Planner", zh: "研究与规划", en: "Research & plan", hint: "明确目标，收集研究依据", hintEn: "Define goals and gather evidence", icon: Search },
  { id: "build", role: "Builder", zh: "开发技能", en: "Build skill", hint: "编写脚本与使用说明", hintEn: "Write code and documentation", icon: Braces },
  { id: "validate", role: "Validator", zh: "独立验收", en: "Verify independently", hint: "实际调用，逐项核对需求", hintEn: "Run the skill and check each goal", icon: ShieldCheck },
  { id: "complete", role: "SearchOS", zh: "保存成果", en: "Save results", hint: "保留技能与验收状态", hintEn: "Save the skill and its verdicts", icon: FileCode2 },
] as const;
const actions: Record<string, [string, string]> = {
  thinking: ["分析下一步", "Considering the next step"], research: ["查阅站点资料", "Reading site references"],
  inspect_source: ["探测页面与核对来源", "Inspecting pages and sources"], plan_ready: ["业务计划已交付", "Capability plan delivered"],
  write_file: ["编写技能文件", "Writing skill files"], edit_file: ["修改技能实现", "Updating implementation"],
  read_file: ["阅读说明与代码", "Reading documentation and code"], execute_cli: ["调用技能进行验证", "Running a skill command"],
  submit_validation: ["提交候选，交给 Validator", "Submitting candidate to Validator"], validation_started: ["开始新一轮独立验收", "Starting a validation round"],
  validation_finished: ["验收报告已返回", "Validation report returned"], repair_started: ["根据反馈开始修复", "Repairing from feedback"],
  handoff: ["提交结论或反馈", "Submitting findings or feedback"], ask_planner: ["向 Planner 澄清需求", "Clarifying requirements with Planner"],
  draft_saved: ["草稿与执行记录已保存", "Draft and execution records saved"], stopped: ["创建已停止", "Creation stopped"],
};
const verdicts: Record<string, [string, string]> = { passed: ["通过", "Passed"], failed: ["失败", "Failed"], incomplete: ["待验收", "Pending"] };
function Verdict({ value, zh }: { value: string; zh: boolean }) {
  const tone = value === "passed" ? "text-ok" : value === "failed" ? "text-err" : "text-ink-faint";
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap text-[11px] ${tone}`}>
    {value === "passed" ? <Check size={12} /> : value === "failed" ? <TriangleAlert size={12} /> : <Circle size={10} />}
    {(verdicts[value] || verdicts.incomplete)[zh ? 0 : 1]}</span>;
}

function displayValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "";
}

export function AgentRoundsView({ rounds, zh }: { rounds: SkillCreationRounds; zh: boolean }) {
  const roles = [["planner", "Planner"], ["builder", "Builder"], ["validator", "Validator"]] as const;
  return <div className="space-y-2">
    {roles.map(([role, label]) => <details key={role} className="group rounded-xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-semibold text-ink">
        {label}<span className="font-normal text-ink-faint">{rounds.roles[role].length} {zh ? "轮" : "turns"}</span>
        <ChevronDown size={14} className="ml-auto group-open:rotate-180" />
      </summary>
      <ol className="max-h-[32rem] space-y-2 overflow-y-auto overscroll-contain border-t border-line p-3">
        {rounds.roles[role].map((round) => <li key={round.number}>
          <details className="group/turn rounded-lg bg-paper">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-ink">
              <span>{zh ? `第 ${round.number} 轮` : `Turn ${round.number}`}</span>
              <span className="text-ink-faint">{round.tool_calls.length} {zh ? "次工具调用" : "tool calls"}</span>
              {round.at && <time className="ml-auto text-[10px] text-ink-faint" dateTime={round.at}>{new Date(round.at).toLocaleTimeString(zh ? "zh-CN" : "en-GB", { hour12: false })}</time>}
              <ChevronDown size={13} className="group-open/turn:rotate-180" />
            </summary>
            <div className="space-y-3 border-t border-line px-3 py-3 text-xs">
              {round.reasoning != null && <div><p className="mb-1 font-semibold text-ink-dim">{zh ? "模型思考" : "Model reasoning"}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface p-3 text-ink-dim">{displayValue(round.reasoning)}</pre></div>}
              <div><p className="mb-1 font-semibold text-ink-dim">{zh ? "模型回复" : "Model response"}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface p-3 text-ink-dim">{displayValue(round.content) || (zh ? "本轮没有文字回复" : "No text response in this turn")}</pre></div>
              {round.tool_calls.map((call, i) => <div key={call.id || i} className="rounded-lg border border-line bg-surface p-3">
                <p className="font-mono font-semibold text-ink">{call.name}</p>
                <p className="mb-1 mt-2 text-ink-faint">{zh ? "调用参数" : "Arguments"}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-ink-dim">{displayValue(call.args)}</pre>
                <p className="mb-1 mt-3 text-ink-faint">{zh ? "工具结果" : "Result"}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-ink-dim">{call.result == null ? (zh ? "尚无已保存结果" : "No saved result yet") : displayValue(call.result)}</pre>
              </div>)}
            </div>
          </details>
        </li>)}
        {!rounds.roles[role].length && <li className="px-2 py-2 text-xs text-ink-faint">{zh ? "暂无轮次记录" : "No turns recorded"}</li>}
      </ol>
    </details>)}
  </div>;
}

function AgentRounds({ job, index, zh }: { job: SkillCreationJob; index: number; zh: boolean }) {
  const [open, setOpen] = useState(false);
  const [rounds, setRounds] = useState<SkillCreationRounds | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setRounds(null);
    setError("");
    if (!open) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await getSkillCreationRounds(job.id, index);
        if (!cancelled) { setRounds(value); setError(""); }
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); }
      finally {
        if (!cancelled && ["running", "queued", "waiting_user"].includes(job.status)) timer = setTimeout(refresh, 3000);
      }
    }
    void refresh();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job.id, job.status, index, open]);
  return <details className="group border-t border-line pt-4" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px] font-semibold text-ink"><Braces size={15} />{zh ? "Agent 每轮思考与工具调用" : "Agent turns and tool calls"}<ChevronDown size={14} className="ml-auto group-open:rotate-180" /></summary>
    <div className="mt-3 space-y-3">
      <p className="text-[11px] leading-5 text-ink-faint">{zh ? "展示已记录的模型回复、可用的思考内容及工具参数和结果。" : "Shows recorded model responses, available reasoning, tool arguments and results."}</p>
      {error ? <p role="alert" className="text-xs text-warn">{error}</p> : rounds ? <AgentRoundsView rounds={rounds} zh={zh} /> : open ? <p role="status" className="text-xs text-ink-faint">{zh ? "读取轮次记录…" : "Loading turns…"}</p> : null}
    </div>
  </details>;
}

export function CreationProgressView({ job, progress, zh, error = "", loading = false, index = 0, onIndex }: {
  job?: SkillCreationJob; progress: Progress | null; zh: boolean; error?: string; loading?: boolean; index?: number; onIndex?: (index: number) => void;
}) {
  const running = !!job && ["running", "queued", "waiting_user"].includes(job.status);
  const waiting = job?.status === "waiting_user";
  const stopped = job?.status === "interrupted";
  const failed = job?.status === "failed";
  const phase = progress?.phase ?? (job?.stage === "site_intent" ? "research" : job?.stage === "access_validation" ? "validate" : job?.stage === "done" ? "complete" : job?.stage === "pipeline" ? "build" : "queued");
  const step = phases.findIndex((item) => item.id === (phase === "repair" ? "build" : phase));
  const caps = progress?.capabilities ?? [];
  const passed = caps.filter((cap) => cap.status === "available").length;
  const pending = caps.length - passed;
  const allPassed = caps.length > 0 && passed === caps.length;
  const title = !job ? (zh ? "创建过程，一目了然" : "Follow every step")
    : waiting ? (zh ? "需要你完成浏览器操作" : "Waiting for your browser action")
    : stopped ? (zh ? "已停止，进展已保存" : "Stopped · progress saved")
    : failed ? (zh ? "创建遇到问题" : "Creation needs attention")
    : job.status === "completed" && job.requests.length === 0 ? (zh ? "无需创建新技能" : "No new skill needed")
    : phase === "repair" ? (zh ? "正在根据验收反馈修复" : "Repairing from validation feedback")
    : phase === "complete" ? (allPassed ? (zh ? "全部能力已通过验收" : "All capabilities verified") : (zh ? "成果已保存，请查看验收结果" : "Results saved · review the verdicts"))
    : phase === "queued" ? (zh ? "等待开始创建" : "Waiting to start")
    : `${zh ? "正在" : "In progress · "}${phases[Math.max(0, step)][zh ? "zh" : "en"]}`;
  const Icon = waiting || failed ? TriangleAlert : stopped ? CirclePause : running ? Loader2 : allPassed ? Check : GitBranch;
  return <section aria-label={zh ? "技能创建流程" : "Skill creation workflow"} className="min-w-0 overflow-hidden rounded-3xl border border-line bg-surface shadow-[0_10px_40px_-26px_rgba(21,34,56,0.2)]">
    <div className="border-b border-line bg-gradient-to-br from-accent/5 via-surface to-surface px-5 pb-6 pt-5 sm:px-7">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <span className="inline-flex items-center gap-2 text-[11px] font-semibold tracking-widest text-accent-ink"><GitBranch size={15} />{zh ? "创建流程" : "CREATION WORKFLOW"}</span>
        {job && <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-faint"><span className={`size-1.5 rounded-full ${running ? "bg-accent" : "bg-ink-faint"}`} />{running ? (zh ? "每 3 秒更新" : "Updates every 3s") : (zh ? "已保存记录" : "Saved activity")}</span>}
      </div>
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl ${waiting || failed ? "bg-warn/10 text-warn" : "bg-accent/10 text-accent-ink"}`}><Icon size={20} className={running && !waiting ? "animate-spin motion-reduce:animate-none" : ""} /></span>
        <div className="min-w-0 flex-1"><h2 aria-live="polite" className="text-[18px] font-semibold leading-7 tracking-tight text-ink">{title}</h2>
          <p className="mt-1 truncate text-[12px] text-ink-dim">{job ? job.input.site || job.input.text : (zh ? "提交需求后，在这里查看研究、开发、验收与修复。" : "Submit a request to follow research, development, validation and repairs.")}</p></div>
      </div>
      {job && job.requests.length > 1 && <label className="mt-4 flex items-center gap-3 text-xs text-ink-dim">{zh ? "当前技能" : "Skill"}<select value={index} onChange={(e) => onIndex?.(Number(e.target.value))} className="min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-ink">{job.requests.map((item, i) => <option key={`${item.category}/${item.name}`} value={i}>{item.name}</option>)}</select></label>}
      <ol className="mt-7 grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-4 sm:gap-x-2" aria-label={zh ? "创建阶段" : "Creation stages"}>
        {phases.map((item, i) => {
          const current = !!job && i === step;
          const calls = item.id === "complete" ? undefined : progress?.calls[item.role.toLowerCase() as keyof Progress["calls"]];
          const reached = !!job && (i < step || (calls ?? 0) > 0);
          const StageIcon = item.icon;
          return <li key={item.id} aria-current={current ? "step" : undefined} title={item[zh ? "hint" : "hintEn"]} className="relative min-w-0">
            {i < 3 && <div aria-hidden="true" className={`absolute left-11 right-0 top-4 hidden border-t sm:block ${reached ? "border-accent/40" : "border-line"}`} />}
            <span className={`relative flex size-8 items-center justify-center rounded-lg border ${current ? "border-accent bg-accent text-white shadow-sm" : reached ? "border-accent/20 bg-accent/10 text-accent-ink" : "border-line bg-surface text-ink-faint"}`}><StageIcon size={15} /></span>
            <span className={`mt-3 block text-[12px] font-semibold ${current ? "text-accent-ink" : reached ? "text-ink" : "text-ink-dim"}`}>{phase === "repair" && i === 1 ? (zh ? "修复技能" : "Repair skill") : item[zh ? "zh" : "en"]}</span>
            <span className="mt-1 block text-[10px] text-ink-faint">{item.role}{calls !== undefined && ` · ${calls} ${zh ? "次调用" : "calls"}`}</span>
          </li>;
        })}
      </ol>
      <div className={`mt-5 flex items-center gap-2 rounded-lg px-3 py-2 text-[11px] ${phase === "repair" ? "bg-warn/10 text-warn" : "bg-paper text-ink-dim"}`}><RefreshCw size={12} className="shrink-0" />{zh ? "验收反馈 → Builder 修复 → Validator 复验" : "Validation feedback → Builder repairs → Validator rechecks"}</div>
    </div>
    {job && <SkillUserAction job={job} zh={zh} />}
    <div className="space-y-6 p-5 sm:p-7">
      {job?.error && <details className="rounded-lg border border-warn/20 bg-warn/5 px-3 py-2 text-xs text-warn"><summary className="cursor-pointer">{zh ? "查看任务提示" : "View job details"}</summary><p className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words leading-5">{job.error}</p></details>}
      {error && <p role="alert" className="rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn">{zh ? "进度暂未更新，正在重试。" : "Progress could not refresh. Retrying."} <span className="break-words">{error}</span></p>}
      {loading && !progress && job && <p role="status" className="flex items-center gap-2 text-xs text-ink-dim"><Loader2 size={13} className="animate-spin" />{zh ? "读取执行记录…" : "Reading execution records…"}</p>}
      <div className="grid grid-cols-3 divide-x divide-line rounded-xl border border-line py-4">
        {[[zh ? "能力已通过" : "Capabilities passed", caps.length ? `${passed} / ${caps.length}` : "—"],
          [zh ? "验收轮次" : "Validation rounds", progress ? progress.validation_rounds : "—"],
          [zh ? "实际执行" : "Executions", progress ? progress.execution_count : "—"]].map(([label, value]) => <div key={label} className="px-2 text-center"><p className="font-mono text-xl font-semibold tabular-nums text-ink">{value}</p><p className="mt-1.5 text-[10px] text-ink-faint">{label}</p></div>)}
      </div>
      <div>
        <div className="mb-3 flex items-center justify-between gap-3"><h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink"><ShieldCheck size={15} />{zh ? "逐项验收" : "Capability checks"}</h3>{caps.length > 0 && <span className="text-[11px] text-ink-faint">{zh ? `${pending} 项待完成` : `${pending} pending`}</span>}</div>
        {phase === "repair" && <p className="mb-3 text-[11px] leading-5 text-ink-dim">{zh ? "候选尚待复验。下方保留上一轮反馈，复验后更新结果。" : "The candidate needs revalidation. Previous findings remain below until then."}</p>}
        {caps.length > 0 ? <div className="overflow-hidden rounded-xl border border-line">
          <div className="hidden grid-cols-[minmax(0,1fr)_70px_70px] gap-2 bg-paper px-4 py-2 text-[10px] text-ink-faint sm:grid"><span>{zh ? "能力 / 验收依据" : "Capability / evidence"}</span><span>{zh ? "执行检查" : "Execution"}</span><span>{zh ? "内容核验" : "Content"}</span></div>
          <ul className="divide-y divide-line">{caps.map((cap) => <li key={cap.id} className="px-3 py-3 sm:px-4">
            <div className="flex flex-wrap items-start gap-x-5 gap-y-2 sm:grid sm:grid-cols-[minmax(0,1fr)_70px_70px] sm:gap-2"><div className="w-full min-w-0"><p className="break-words text-[12px] font-medium leading-5 text-ink">{cap.id === "package" ? (zh ? "技能基础检查" : "Package checks") : cap.purpose}</p><p className="mt-0.5 break-all font-mono text-[10px] text-ink-faint">{cap.id}</p></div><span className="inline-flex items-center gap-2"><span className="text-[10px] text-ink-faint sm:hidden">{zh ? "执行" : "Execution"}</span><Verdict value={cap.deterministic} zh={zh} /></span><span className="inline-flex items-center gap-2"><span className="text-[10px] text-ink-faint sm:hidden">{zh ? "内容" : "Content"}</span><Verdict value={cap.semantic} zh={zh} /></span></div>
            {cap.external_blocked && <p className="mt-2 text-[11px] text-warn">{zh ? "等待站点访问条件恢复" : "Waiting for site access"}</p>}
            {cap.reason && <details className="mt-2 text-[11px] leading-5 text-ink-dim"><summary className="cursor-pointer text-ink-faint">{phase === "repair" ? (zh ? "上次验收说明" : "Previous findings") : (zh ? "查看验收说明" : "View findings")}{cap.executions > 0 && ` · ${cap.executions} ${zh ? "次执行" : "executions"}`}</summary><p className="mt-1 whitespace-pre-wrap break-words">{cap.reason}</p></details>}
          </li>)}</ul></div> : <div className="rounded-xl border border-dashed border-line-strong p-6 text-center text-xs leading-6 text-ink-faint"><FlaskConical size={22} className="mx-auto mb-2 opacity-60" />{zh ? "计划形成后，这里会逐项展示能力和验收结果。" : "Capability checks will appear once the plan is ready."}</div>}
      </div>
      {!!progress?.regressions.length && <div className="rounded-xl border border-warn/20 bg-warn/5 p-4"><h3 className="flex items-center gap-2 text-xs font-medium text-warn"><RefreshCw size={13} />{zh ? `${progress.regressions.length} 个原失败输入待复验` : `${progress.regressions.length} original failures to recheck`}</h3><ul className="mt-2 space-y-1 text-[11px] leading-5 text-ink-dim">{progress.regressions.slice(0, 5).map((item, i) => <li key={i} className="break-words">{item.capability_id} · {item.reason}</li>)}</ul></div>}
      <div>
        <div className="mb-4 flex items-center justify-between"><h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink"><Clock3 size={15} />{zh ? "最近动态" : "Recent activity"}</h3>{progress?.last_activity && <time className="text-[10px] tabular-nums text-ink-faint" dateTime={progress.last_activity}>{new Date(progress.last_activity).toLocaleTimeString(zh ? "zh-CN" : "en-GB", { hour12: false })}</time>}</div>
        {progress?.events.length ? <ol className="max-h-56 space-y-0 overflow-y-auto overscroll-contain pr-2">{progress.events.slice().reverse().map((event, i) => <li key={`${event.at}-${i}`} className="relative flex gap-3 pb-4 text-[11px] last:pb-0"><span aria-hidden="true" className="relative mt-1 w-2 shrink-0"><span className={`relative z-10 block size-1.5 rounded-full ${i === 0 ? "bg-accent" : "bg-line-strong"}`} /><span className="absolute left-[2px] top-2 h-[calc(100%+12px)] border-l border-line" /></span><div className="min-w-0 flex-1"><p className="text-ink-dim">{(actions[event.action] || [event.action, event.action])[zh ? 0 : 1]}</p>{event.role && <span className="mt-1 block text-[10px] capitalize text-ink-faint">{event.role}</span>}</div><time className="shrink-0 tabular-nums text-ink-faint" dateTime={event.at}>{new Date(event.at).toLocaleTimeString(zh ? "zh-CN" : "en-GB", { hour12: false })}</time></li>)}</ol> : <p className="py-3 text-xs text-ink-faint">{zh ? "执行开始后，角色交接与操作记录会显示在这里。" : "Role handoffs and actions will appear when execution starts."}</p>}
      </div>
      {job && <AgentRounds key={`${job.id}-${index}`} job={job} index={index} zh={zh} />}
      {!!progress?.files.length && <details className="group border-t border-line pt-4"><summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-ink-dim"><FileCode2 size={14} />{zh ? `已保存 ${progress.files.length} 个文件` : `${progress.files.length} files saved`}<ChevronDown size={13} className="ml-auto group-open:rotate-180" /></summary><ul className="mt-3 space-y-1 font-mono text-[11px] text-ink-faint">{progress.files.map((file) => <li key={file} className="break-all">{file}</li>)}</ul></details>}
      {!job && <p className="flex items-center gap-2 text-[11px] text-accent-ink"><ArrowRight size={13} />{zh ? "从左侧填写需求，开始创建" : "Start with a request in the form"}</p>}
    </div>
  </section>;
}

export default function SkillCreationProgress({ job, zh }: { job?: SkillCreationJob; zh: boolean }) {
  const [index, setIndex] = useState(0);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const selectedIndex = Math.min(index, Math.max(0, (job?.requests.length ?? 1) - 1));
  const id = job?.id;
  const status = job?.status;
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await getSkillCreationProgress(id!, selectedIndex);
        if (!cancelled) { setProgress(result); setError(""); }
      } catch (e) { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); }
      finally {
        if (!cancelled) { setLoading(false); timer = setTimeout(poll, ["running", "queued", "waiting_user"].includes(status ?? "") ? 3000 : 15000); }
      }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, selectedIndex, status]);
  const current = progress && progress.job_id === id && progress.request_index === selectedIndex ? progress : null;
  return <CreationProgressView job={job} progress={current} zh={zh} error={error} loading={loading} index={selectedIndex} onIndex={setIndex} />;
}
