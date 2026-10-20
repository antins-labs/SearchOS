"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Check, ChevronDown, Clock3, Globe2, History, Loader2, RotateCcw, Square, Trash2, TriangleAlert } from "lucide-react";
import type { SkillCreationInput, SkillCreationJob } from "@/lib/api";
import SkillDraftEditor from "./SkillDraftEditor";

type Resume = (id: string, index: number) => void;
type ManagementAction = { kind: "delete" | "cancel"; ids: string[] };

const isActive = (job: SkillCreationJob) => job.status === "running" || job.status === "queued";
const statusLabels: Record<string, string> = { queued: "排队中", running: "进行中", completed: "已完成", partial: "部分完成", failed: "创建失败", interrupted: "已中断", installed: "已入库", build_failed: "生成失败", validation_failed: "验证未通过", error: "执行错误" };

function failureSummary(error: string) {
  try { const report = JSON.parse(error); return String(report.error || report.model_error || report.exit_reason || error); }
  catch { return error; }
}

function JobCard({ job, zh, disabled, repairing, managing, selected, working, onSelect, onAction, onRetry, onResume }: { job: SkillCreationJob; zh: boolean; disabled: boolean; repairing: number[]; managing: boolean; selected: boolean; working: boolean; onSelect: () => void; onAction: (action: ManagementAction) => void; onRetry: (input: SkillCreationInput) => void; onResume: Resume }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const running = isActive(job);
  const empty = job.status === "completed" && job.requests.length === 0;
  const failed = ["failed", "partial", "interrupted"].includes(job.status);
  const installed = job.results.filter((r) => r.status === "installed").length;
  const repairable = job.requests.some((r, index) => (r.can_resume ?? r.has_draft) && job.results[index]?.status !== "installed");
  const hasDraft = job.requests.some((r, index) => r.has_draft && job.results[index]?.status !== "installed");
  const title = job.input.site ? job.input.site.replace(/^https?:\/\//, "").replace(/\/$/, "") : job.input.text;
  const tone = running ? "bg-accent/10 text-accent-ink" : failed ? "bg-warn/10 text-warn" : empty ? "bg-surface-2 text-ink-dim" : "bg-ok/10 text-ok";
  const planning = ["queued", "intent", "planned", "site_intent"].includes(job.stage);
  const progressText = job.stage === "site_intent" ? (zh ? "正在规划站点能力…" : "Planning site capabilities…")
    : planning ? (zh ? "正在分析需求…" : "Analyzing your request…")
    : (zh ? `正在生成与验证 · ${job.results.length} / ${job.requests.length}` : `Generating and validating · ${job.results.length} / ${job.requests.length}`);
  const label = (value: string) => zh ? statusLabels[value] ?? value : value.replaceAll("_", " ");
  return <article className="overflow-hidden rounded-2xl border border-line bg-surface">
    <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)} className="group w-full p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-medium ${tone}`}>
          {running ? <Loader2 size={11} className="animate-spin" /> : failed ? <TriangleAlert size={11} /> : empty ? <Globe2 size={11} /> : <Check size={11} />}
          {empty ? (zh ? "无需新建" : "No new skill needed") : failed && repairable ? (hasDraft ? (zh ? "草稿待修复" : "Draft needs repair") : (zh ? "可继续创建" : "Ready to continue")) : label(job.status)}
        </span>
        <time className="text-[10px] tabular-nums text-ink-faint" dateTime={job.created_at}>{new Date(job.created_at).toLocaleString(zh ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
      </div>
      <div className="flex items-start gap-3"><h3 className="line-clamp-2 min-w-0 flex-1 break-all text-[13px] font-medium leading-6 text-ink">{title}</h3><ChevronDown size={14} className={`mt-1 shrink-0 text-ink-faint transition-transform ${expanded ? "rotate-180" : ""}`} /></div>
      <p className="mt-1 text-[11px] leading-5 text-ink-dim">{empty ? (zh ? "已有能力可复用，或暂无需要创建的技能。" : "Existing skills may cover this request, or no reusable gap was found.") : running ? progressText : (zh ? `${installed} 个技能入库 · 点击查看详情` : `${installed} installed · View details`)}</p>
      {running && <div className="mt-3 flex gap-1" aria-label={zh ? "创建进度" : "Creation progress"}>{["intent", "pipeline", "done"].map((stage, index) => <span key={stage} className={`h-1 flex-1 rounded-full ${index === 0 || index === 1 && !planning ? "bg-accent/70" : "bg-surface-2"}`} />)}</div>}
    </button>
    {expanded && <div className="space-y-3 border-t border-line px-4 py-3 text-[12px] leading-6">
      {job.resume_of && <p className="text-[11px] text-ink-faint">{job.resume_kind === "site_session" ? (zh ? "继续创建 · 复用已保存的站点研究" : "Continued creation · Reuses saved site research") : (zh ? "续修记录 · 使用原有草稿继续验证" : "Repair attempt · Continues from the saved draft")}</p>}
      {job.error && <p className="break-words text-err">{job.error}</p>}
      {job.requests.map((request, index) => {
        const result = job.results[index];
        const planningFailed = result?.failure_stage === "site_intent" || result?.error?.startsWith("site intent call budget exhausted");
        return <div key={`${request.category}/${request.name}`} className="space-y-1">
          <p className="break-all font-medium text-ink">{request.name}</p>
          <p className="text-[10px] text-ink-faint">{request.category} · {request.action === "update" ? (zh ? "更新" : "Update") : (zh ? "新建" : "Create")} · {planningFailed ? (zh ? "需求规划未完成" : "Site planning incomplete") : result ? label(result.status) : running ? (zh ? "等待完成" : "Pending") : label("interrupted")}</p>
          <p className="text-ink-dim">{request.description}</p>
          {request.subtask && <p className="text-ink-dim">{zh ? "验证任务：" : "Validation: "}{request.subtask}</p>}
          {planningFailed && <p className="text-ink-dim">{zh ? "站点能力计划尚未通过校验，脚本生成尚未开始。" : "The site capability plan has not passed validation; script generation has not started."}</p>}
          {result?.error && <p className="whitespace-pre-wrap break-words text-err">{failureSummary(result.error)}</p>}
          {(result?.path || result?.trial_path) && <details className="text-[11px] text-ink-faint"><summary className="cursor-pointer">{zh ? "文件与验证记录" : "Files and validation"}</summary><p className="break-all">{result.path}</p><p className="break-all">{result.trial_path}</p></details>}
          {(request.has_draft || request.can_resume) && <div className="flex flex-wrap gap-2 pt-2">
            {request.has_draft && <button type="button" onClick={() => setEditing(index)} className="rounded-lg border border-line px-3 py-1.5 text-ink-dim hover:text-ink">{zh ? "查看 / 编辑草稿" : "View / edit draft"}</button>}
            {!running && result?.status !== "installed" && (request.can_resume ?? request.has_draft) && <button type="button" disabled={disabled || repairing.includes(index)} onClick={() => onResume(job.id, index)} className="inline-flex items-center gap-1.5 rounded-lg bg-accent/10 px-3 py-1.5 text-accent-ink disabled:opacity-40"><RotateCcw size={12} />{repairing.includes(index) ? (zh ? "继续创建中" : "Continuing") : request.has_draft ? (zh ? "继续修复" : "Continue repair") : (zh ? "继续创建" : "Continue creation")}</button>}
          </div>}
        </div>;
      })}
      {failed && !repairable && <button type="button" disabled={disabled} onClick={() => onRetry(job.input)} className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2 px-3 py-1.5 text-ink-dim hover:text-ink disabled:opacity-40"><RotateCcw size={12} />{zh ? "重新分析并生成" : "Analyze and generate again"}</button>}
    </div>}
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2 text-[11px]">
      {managing ? <label className="flex items-center gap-2 text-ink-dim">
        <input type="checkbox" checked={selected} onChange={onSelect} disabled={working || running || repairing.length > 0} aria-label={zh ? `选择记录：${title}` : `Select record: ${title}`} className="accent-accent" />
        {running ? (zh ? "进行中" : "In progress") : repairing.length > 0 ? (zh ? "继续创建中" : "Continuation in progress") : (zh ? "选择" : "Select")}
      </label> : <span className="text-ink-faint">{repairing.length > 0 ? (zh ? "继续创建中" : "Continuation in progress") : ""}</span>}
      <button type="button" disabled={working || (!running && repairing.length > 0)} onClick={() => onAction({ kind: running ? "cancel" : "delete", ids: [job.id] })} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-ink-dim hover:bg-err/5 hover:text-err disabled:cursor-not-allowed disabled:opacity-40">
        {running ? <Square size={12} /> : <Trash2 size={12} />}{running ? (zh ? "停止创建" : "Stop creation") : (zh ? "删除记录" : "Delete record")}
      </button>
    </div>
    {editing !== null && <SkillDraftEditor job={job} index={editing} zh={zh} disabled={disabled} locked={repairing.includes(editing)} onClose={() => setEditing(null)} onResume={onResume} />}
  </article>;
}

function ManagementDialog({ action, zh, busy, error, onClose, onConfirm }: { action: ManagementAction; zh: boolean; busy: boolean; error: string; onClose: () => void; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close(); }, []);
  const deleting = action.kind === "delete";
  return <dialog ref={dialog} onCancel={(e) => { e.preventDefault(); if (!busy) onClose(); }} aria-labelledby="creation-management-title" className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-sm rounded-2xl border border-line bg-surface p-6 text-ink shadow-xl backdrop:bg-ink/25">
    <h3 id="creation-management-title" className="text-base font-semibold">{deleting ? (zh ? `删除 ${action.ids.length} 条创建记录？` : `Delete ${action.ids.length} creation record(s)?`) : (zh ? "停止这次创建？" : "Stop this creation?")}</h3>
    <p className="mt-3 text-sm leading-6 text-ink-dim">{deleting ? (zh ? "将删除所选记录、草稿和验证日志，无法撤销。已入库的技能会保留。" : "Selected records, drafts and validation logs will be permanently deleted. Installed skills will be kept.") : (zh ? "停止后会保留研究记录、草稿和已入库技能，可从创建记录中继续。" : "Research, drafts and installed skills will be kept. You can continue from the record.")}</p>
    {error && <p role="alert" className="mt-3 text-xs text-err">{error}</p>}
    <div className="mt-6 flex justify-end gap-3 text-sm">
      <button type="button" autoFocus disabled={busy} onClick={onClose} className="rounded-lg border border-line px-4 py-2 disabled:opacity-40">{zh ? "取消" : "Cancel"}</button>
      <button type="button" disabled={busy} onClick={onConfirm} className="inline-flex items-center gap-2 rounded-lg bg-err px-4 py-2 text-white disabled:opacity-40">{busy && <Loader2 size={14} className="animate-spin" />}{busy ? (zh ? "处理中…" : "Working…") : deleting ? (zh ? "确认删除" : "Delete") : (zh ? "停止创建" : "Stop creation")}</button>
    </div>
  </dialog>;
}

export default function SkillCreationHistory({ jobs, zh, loading, error, disabled, onRetry, onResume, onDelete, onCancel }: { jobs: SkillCreationJob[]; zh: boolean; loading: boolean; error: string; disabled: boolean; onRetry: (input: SkillCreationInput) => void; onResume: Resume; onDelete: (ids: string[]) => Promise<void>; onCancel: (id: string) => Promise<void> }) {
  const [managing, setManaging] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState<ManagementAction | null>(null);
  const [working, setWorking] = useState(false);
  const [actionError, setActionError] = useState("");
  const inFlight = useRef(false);
  const repairing = (id: string) => jobs.filter((j) => isActive(j) && j.resume_of?.job_id === id).map((j) => j.resume_of!.index);
  const eligible = jobs.filter((job) => !isActive(job) && !repairing(job.id).length).map((job) => job.id);
  const selection = selected.filter((id) => eligible.includes(id));
  function requestAction(action: ManagementAction) { setActionError(""); setPending(action); }
  async function confirm() {
    if (!pending || inFlight.current) return;
    inFlight.current = true; setWorking(true); setActionError("");
    try {
      if (pending.kind === "delete") { await onDelete(pending.ids); setSelected((old) => old.filter((id) => !pending.ids.includes(id))); }
      else await onCancel(pending.ids[0]);
      setPending(null);
    } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); }
    finally { inFlight.current = false; setWorking(false); }
  }
  return <aside className="min-w-0 lg:pl-2">
    <div className="mb-5 flex items-center justify-between"><h2 className="flex items-center gap-2 text-[14px] font-semibold text-ink"><History size={16} className="text-ink-dim" />{zh ? "创建记录" : "Activity"}</h2><button type="button" disabled={loading || working || !jobs.length} onClick={() => { setManaging(!managing); setSelected([]); }} className="rounded-lg px-2 py-1 text-[12px] text-accent-ink hover:bg-accent/5 disabled:opacity-40">{managing ? (zh ? "完成" : "Done") : (zh ? "管理" : "Manage")}</button></div>
    {managing && <div className="mb-4 flex items-center justify-between gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-[11px]">
      <label className="flex items-center gap-2 text-ink-dim"><input type="checkbox" aria-label={zh ? "全选可删除记录" : "Select all deletable records"} checked={eligible.length > 0 && selection.length === eligible.length} disabled={working || !eligible.length} onChange={(e) => setSelected(e.target.checked ? eligible : [])} className="accent-accent" />{zh ? `已选 ${selection.length}` : `${selection.length} selected`}</label>
      <button type="button" disabled={working || !selection.length} onClick={() => requestAction({ kind: "delete", ids: selection })} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-err hover:bg-err/5 disabled:opacity-40"><Trash2 size={12} />{zh ? "删除所选" : "Delete selected"}</button>
    </div>}
    {error && <p role="alert" className="mb-3 rounded-xl bg-err/5 p-3 text-[12px] text-err">{error}</p>}
    {loading ? <p role="status" className="flex items-center gap-2 text-[12px] text-ink-dim"><Loader2 size={14} className="animate-spin" />{zh ? "正在读取记录…" : "Loading activity…"}</p> : !jobs.length && !error ? <div className="rounded-2xl border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="mx-auto mb-4 flex size-10 items-center justify-center rounded-full bg-surface-2 text-ink-faint"><Clock3 size={19} /></div>
      <p className="text-[13px] font-medium text-ink-dim">{zh ? "第一个技能，从这里开始" : "Your first skill starts here"}</p><p className="mt-2 text-[12px] leading-6 text-ink-faint">{zh ? "提交后，生成进度和验证结果会显示在这里。" : "Generation progress and validation results will appear here."}</p>
    </div> : <div className="space-y-3">{jobs.map((job) => <JobCard key={job.id} job={job} zh={zh} disabled={disabled || working} repairing={repairing(job.id)} managing={managing} selected={selection.includes(job.id)} working={working} onSelect={() => setSelected((old) => old.includes(job.id) ? old.filter((id) => id !== job.id) : [...old, job.id])} onAction={requestAction} onRetry={onRetry} onResume={onResume} />)}</div>}
    <p className="mt-5 flex items-center gap-1.5 text-[11px] text-ink-faint"><ArrowUpRight size={13} />{zh ? "离开页面后，已提交的创建任务仍会继续。" : "Submitted jobs continue after you leave."}</p>
    {pending && <ManagementDialog action={pending} zh={zh} busy={working} error={actionError} onClose={() => setPending(null)} onConfirm={() => void confirm()} />}
  </aside>;
}
