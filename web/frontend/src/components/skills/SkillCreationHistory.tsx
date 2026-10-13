"use client";

import { useState } from "react";
import { ArrowUpRight, Check, ChevronDown, Clock3, Globe2, History, Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import type { SkillCreationInput, SkillCreationJob } from "@/lib/api";

const isActive = (job: SkillCreationJob) => job.status === "running" || job.status === "queued";
const statusLabels: Record<string, string> = { queued: "排队中", running: "进行中", completed: "已完成", partial: "部分完成", failed: "创建失败", interrupted: "已中断", installed: "已入库", build_failed: "生成失败", validation_failed: "验证未通过", error: "执行错误" };

function JobCard({ job, zh, disabled, onRetry }: { job: SkillCreationJob; zh: boolean; disabled: boolean; onRetry: (input: SkillCreationInput) => void }) {
  const [expanded, setExpanded] = useState(false);
  const running = isActive(job);
  const empty = job.status === "completed" && job.requests.length === 0;
  const failed = ["failed", "partial", "interrupted"].includes(job.status);
  const installed = job.results.filter((r) => r.status === "installed").length;
  const title = job.input.site ? job.input.site.replace(/^https?:\/\//, "").replace(/\/$/, "") : job.input.text;
  const tone = running ? "bg-accent/10 text-accent-ink" : failed ? "bg-warn/10 text-warn" : empty ? "bg-surface-2 text-ink-dim" : "bg-ok/10 text-ok";
  const label = (value: string) => zh ? statusLabels[value] ?? value : value.replaceAll("_", " ");
  return <article className="overflow-hidden rounded-2xl border border-line bg-surface">
    <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)} className="group w-full p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-medium ${tone}`}>
          {running ? <Loader2 size={11} className="animate-spin" /> : failed ? <TriangleAlert size={11} /> : empty ? <Globe2 size={11} /> : <Check size={11} />}
          {empty ? (zh ? "无需新建" : "No new skill needed") : label(job.status)}
        </span>
        <time className="text-[10px] tabular-nums text-ink-faint" dateTime={job.created_at}>{new Date(job.created_at).toLocaleString(zh ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
      </div>
      <div className="flex items-start gap-3"><h3 className="line-clamp-2 min-w-0 flex-1 break-all text-[13px] font-medium leading-6 text-ink">{title}</h3><ChevronDown size={14} className={`mt-1 shrink-0 text-ink-faint transition-transform ${expanded ? "rotate-180" : ""}`} /></div>
      <p className="mt-1 text-[11px] leading-5 text-ink-dim">{empty ? (zh ? "已有能力可复用，或暂无需要创建的技能。" : "Existing skills may cover this request, or no reusable gap was found.") : running ? (job.stage === "intent" ? (zh ? "正在分析需求…" : "Analyzing your request…") : (zh ? `正在生成与验证 · ${job.results.length} / ${job.requests.length}` : `Generating and validating · ${job.results.length} / ${job.requests.length}`)) : (zh ? `${installed} 个技能入库 · 点击查看详情` : `${installed} installed · View details`)}</p>
      {running && <div className="mt-3 flex gap-1" aria-label={zh ? "创建进度" : "Creation progress"}>{["intent", "pipeline", "done"].map((stage, index) => <span key={stage} className={`h-1 flex-1 rounded-full ${index === 0 || index === 1 && job.stage !== "intent" && job.stage !== "queued" ? "bg-accent/70" : "bg-surface-2"}`} />)}</div>}
    </button>
    {expanded && <div className="space-y-3 border-t border-line px-4 py-3 text-[12px] leading-6">
      {job.error && <p className="break-words text-err">{job.error}</p>}
      {job.requests.map((request, index) => {
        const result = job.results[index];
        return <div key={`${request.category}/${request.name}`} className="space-y-1">
          <p className="break-all font-medium text-ink">{request.name}</p>
          <p className="text-[10px] text-ink-faint">{request.category} · {request.action === "update" ? (zh ? "更新" : "Update") : (zh ? "新建" : "Create")} · {result ? label(result.status) : running ? (zh ? "等待完成" : "Pending") : label("interrupted")}</p>
          <p className="text-ink-dim">{request.description}</p>
          {request.subtask && <p className="text-ink-dim">{zh ? "验证任务：" : "Validation: "}{request.subtask}</p>}
          {result?.error && <p className="whitespace-pre-wrap break-words text-err">{result.error}</p>}
          {(result?.path || result?.trial_path) && <details className="text-[11px] text-ink-faint"><summary className="cursor-pointer">{zh ? "文件与验证记录" : "Files and validation"}</summary><p className="break-all">{result.path}</p><p className="break-all">{result.trial_path}</p></details>}
        </div>;
      })}
      {failed && <button type="button" disabled={disabled} onClick={() => onRetry(job.input)} className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-1.5 text-ink-dim hover:text-ink disabled:opacity-40"><RotateCcw size={12} />{zh ? "重试未完成部分" : "Retry unfinished work"}</button>}
    </div>}
  </article>;
}

export default function SkillCreationHistory({ jobs, zh, loading, error, disabled, onRetry }: { jobs: SkillCreationJob[]; zh: boolean; loading: boolean; error: string; disabled: boolean; onRetry: (input: SkillCreationInput) => void }) {
  return <aside className="min-w-0 lg:pl-2">
    <div className="mb-5 flex items-center justify-between"><h2 className="flex items-center gap-2 text-[14px] font-semibold text-ink"><History size={16} className="text-ink-dim" />{zh ? "创建记录" : "Activity"}</h2><span className="text-[11px] text-ink-faint">{zh ? "自动保存" : "Autosaved"}</span></div>
    {error && <p role="alert" className="mb-3 rounded-xl bg-err/5 p-3 text-[12px] text-err">{error}</p>}
    {loading ? <p role="status" className="flex items-center gap-2 text-[12px] text-ink-dim"><Loader2 size={14} className="animate-spin" />{zh ? "正在读取记录…" : "Loading activity…"}</p> : !jobs.length && !error ? <div className="rounded-2xl border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="mx-auto mb-4 flex size-10 items-center justify-center rounded-full bg-surface-2 text-ink-faint"><Clock3 size={19} /></div>
      <p className="text-[13px] font-medium text-ink-dim">{zh ? "第一个技能，从这里开始" : "Your first skill starts here"}</p><p className="mt-2 text-[12px] leading-6 text-ink-faint">{zh ? "提交后，生成进度和验证结果会显示在这里。" : "Generation progress and validation results will appear here."}</p>
    </div> : <div className="space-y-3">{jobs.slice(0, 20).map((job) => <JobCard key={job.id} job={job} zh={zh} disabled={disabled} onRetry={onRetry} />)}</div>}
    <p className="mt-5 flex items-center gap-1.5 text-[11px] text-ink-faint"><ArrowUpRight size={13} />{zh ? "离开页面后，已提交的创建任务仍会继续。" : "Submitted jobs continue after you leave."}</p>
  </aside>;
}
