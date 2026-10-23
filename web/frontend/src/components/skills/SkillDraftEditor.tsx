"use client";

import { useEffect, useRef, useState } from "react";
import { X, Save, Play, FileCode2, RefreshCw } from "lucide-react";
import { getSkillDraft, getSkillDraftFile, saveSkillDraftFile, type SkillCreationJob, type SkillDraft } from "@/lib/api";
import Select from "@/components/ui/Select";

export default function SkillDraftEditor({ job, index, zh, disabled, locked, onClose, onResume }: {
  job: SkillCreationJob; index: number; zh: boolean; disabled: boolean; locked: boolean;
  onClose: () => void; onResume: (id: string, index: number) => void;
}) {
  const [draft, setDraft] = useState<SkillDraft | null>(null);
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [original, setOriginal] = useState("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [reload, setReload] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const dirty = content !== original;
  const installed = job.results[index]?.status === "installed";
  const editable = !locked && !installed && !["running", "queued"].includes(job.status);

  useEffect(() => {
    const element = dialog.current;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element?.showModal();
    return () => { element?.close(); document.body.style.overflow = previous; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getSkillDraft(job.id, index).then((value) => {
      if (!cancelled) { setDraft(value); setPath((previous) => value.files.includes(previous) ? previous : value.files.includes("SKILL.md") ? "SKILL.md" : value.files[0] ?? ""); }
    }).catch((e) => { if (!cancelled) setError(String(e.message || e)); });
    return () => { cancelled = true; };
  }, [job.id, index, reload]);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setBusy(true); setError("");
    getSkillDraftFile(job.id, index, path).then((file) => {
      if (!cancelled) { setContent(file.content); setOriginal(file.content); setRevision(file.revision); }
    }).catch((e) => { if (!cancelled) setError(String(e.message || e)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [job.id, index, path, reload]);

  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      const updated = await saveSkillDraftFile(job.id, index, { path, content, revision });
      setDraft(updated); setRevision(updated.revision); setOriginal(content);
      setMessage(zh ? "已保存新草稿版本，继续修复时会重新验证。" : "Draft saved. Validation runs again when you resume.");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return <dialog ref={dialog} onCancel={(e) => { e.preventDefault(); if (!dirty && !busy) onClose(); }} className="fixed inset-0 ml-auto h-dvh max-h-none w-full max-w-4xl bg-surface p-0 text-ink backdrop:bg-ink/25" aria-label={zh ? "草稿与验证记录" : "Draft and validation"}>
    <section className="flex h-full w-full max-w-4xl flex-col bg-surface shadow-xl">
      <header className="flex items-center justify-between border-b border-line px-6 py-4">
        <div><h2 className="font-semibold text-ink">{job.requests[index].name}</h2><p className="mt-1 text-xs text-ink-dim">{zh ? "草稿与验证记录 · 保存后仍需验证才能入库" : "Draft and validation · Publishing requires validation"}</p></div>
        <div className="flex items-center gap-4">
          <button type="button" disabled={busy || dirty} onClick={() => setReload((n) => n + 1)} className="flex items-center gap-1 text-xs text-ink-dim disabled:opacity-40"><RefreshCw size={14} />{zh ? "刷新记录" : "Refresh"}</button>
          <button type="button" onClick={onClose} disabled={busy} className="flex items-center gap-1 text-xs text-ink-dim" aria-label={zh ? "关闭草稿" : "Close draft"}><X size={18} />{dirty ? (zh ? "关闭，不保存" : "Close without saving") : ""}</button>
        </div>
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-6">
        <p className="text-sm leading-6 text-ink-dim">{job.requests[index].description}</p>
        {job.resume_of && <p className="text-xs text-ink-faint">{zh ? "续修自记录：" : "Resumed from: "}{job.resume_of.job_id}</p>}
        {locked && <p className="text-xs text-accent-ink">{zh ? "该草稿正在续修。请查看最新的续修记录，完成后可继续编辑。" : "This draft is being repaired. Open the latest repair record to follow progress."}</p>}
        {["running", "queued"].includes(job.status) && <p className="text-xs text-accent-ink">{zh ? "任务进行中，草稿只读。可刷新记录查看最新进展。" : "Job in progress. This draft is read-only; refresh to see updates."}</p>}
        <details open className="rounded-xl border border-line p-3 text-xs text-ink-dim">
          <summary className="cursor-pointer font-medium">{zh ? "验证结果与执行记录" : "Validation and execution records"}</summary>
          <pre className="mt-3 max-h-52 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify({ validation: draft?.validation, execution: draft?.diagnostics, examples: draft?.examples }, null, 2)}</pre>
        </details>
        {!!draft?.events.length && <details className="rounded-xl border border-line p-3 text-xs text-ink-dim">
          <summary className="cursor-pointer font-medium">{zh ? "最近的执行轨迹（最多 40 条）" : "Recent execution trace (up to 40 events)"}</summary>
          <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(draft.events, null, 2)}</pre>
        </details>}
        {!draft && !error && <p role="status">{zh ? "读取草稿中…" : "Loading draft…"}</p>}
        {draft && <>
          <label className="flex items-center gap-2 text-xs text-ink-dim"><FileCode2 size={15} />{zh ? "草稿文件" : "Draft file"}
            <Select ariaLabel={zh ? "草稿文件" : "Draft file"} value={path} placeholder="" onChange={(next) => { if (next === path) return; setPath(next); setMessage(""); }} disabled={busy || dirty} className="min-w-0 flex-1" options={draft.files.map((file) => ({ value: file, label: file }))} />
          </label>
          <textarea aria-label={zh ? "草稿内容" : "Draft content"} spellCheck={false} value={content} onChange={(e) => setContent(e.target.value)} readOnly={!editable || busy || !!error} className="h-[45vh] w-full rounded-xl border border-line bg-paper p-4 font-mono text-xs leading-5 text-ink outline-none focus:border-accent" />
        </>}
        {error && <div role="alert" className="text-sm text-err">{error}<button type="button" disabled={busy} onClick={() => { setError(""); setReload((n) => n + 1); }} className="ml-3 underline">{zh ? "重新读取（放弃编辑）" : "Reload (discard edits)"}</button></div>}
        {message && <p role="status" className="text-sm text-ok">{message}</p>}
      </div>
      <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-line px-6 py-4 text-sm">
        {dirty && <button type="button" disabled={busy} onClick={() => { setContent(original); setError(""); }}>{zh ? "撤销编辑" : "Discard edits"}</button>}
        <button type="button" onClick={() => void save()} disabled={!editable || !dirty || busy || !!error} className="flex items-center gap-2 rounded-lg border border-line px-4 py-2 disabled:opacity-40"><Save size={14} />{zh ? "保存草稿" : "Save draft"}</button>
        <button type="button" onClick={() => { onResume(job.id, index); onClose(); }} disabled={!editable || disabled || dirty || busy || !draft || !!error} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-white disabled:opacity-40"><Play size={14} />{zh ? "继续修复" : "Continue repair"}</button>
      </footer>
    </section>
  </dialog>;
}
