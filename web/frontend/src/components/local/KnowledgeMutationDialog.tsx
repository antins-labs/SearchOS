"use client";

import { useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import useDialogFocus from "@/hooks/useDialogFocus";

export default function KnowledgeMutationDialog({ title, name = "", summary, description, deleting, onSave, onClose }: {
  title: string;
  name?: string;
  summary?: string;
  description: string;
  deleting?: boolean;
  onSave: (name: string, summary: string) => Promise<void>;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState(name);
  const [recap, setRecap] = useState(summary ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const close = () => { if (!busy) onClose(); };
  useDialogFocus({ containerRef: ref, initialFocusRef: cancelRef, onClose: close });
  return <div className="absolute inset-0 z-30 grid place-items-center bg-ink/25 p-4 dark:bg-black/55" onMouseDown={close}>
    <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="knowledge-mutation-title" tabIndex={-1}
      onMouseDown={(event) => event.stopPropagation()} className="surface w-full max-w-md rounded-2xl border border-line p-5 shadow-xl">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="knowledge-mutation-title" className="text-base font-semibold text-ink">{title}</h2>
        <button type="button" disabled={busy} onClick={close} aria-label="关闭操作窗口" className="rounded p-1 text-ink-dim disabled:opacity-40"><X size={16} /></button>
      </div>
      <p className="mb-4 whitespace-pre-wrap break-words text-sm leading-6 text-ink-dim">{description}</p>
      <form onSubmit={async (event) => {
        event.preventDefault();
        if (busy || (!deleting && !draft.trim())) return;
        setBusy(true); setError(null);
        try { await onSave(draft.trim(), recap.trim()); onClose(); }
        catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
        finally { setBusy(false); }
      }}>
        {!deleting && <fieldset disabled={busy} className="space-y-3">
          <label className="block text-xs text-ink-dim">名称
            <input aria-label="名称" required maxLength={120} value={draft} onChange={(event) => setDraft(event.target.value)}
              className="mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent" />
          </label>
          {summary !== undefined && <label className="block text-xs text-ink-dim">主题说明
            <textarea aria-label="主题说明" maxLength={5000} rows={4} value={recap} onChange={(event) => setRecap(event.target.value)}
              className="mt-1 w-full resize-y rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent" />
          </label>}
        </fieldset>}
        {error && <p role="alert" className="mt-3 break-words text-sm text-err">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button ref={cancelRef} type="button" disabled={busy} onClick={close} className="rounded-lg border border-line px-4 py-2 text-sm text-ink-dim disabled:opacity-40">取消</button>
          <button type="submit" disabled={busy || (!deleting && !draft.trim())}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm disabled:opacity-40 ${deleting ? "bg-err text-white" : "bg-ink text-paper"}`}>
            {busy && <Loader2 size={14} className="animate-spin" />}{busy ? "处理中…" : deleting ? "确认删除" : "保存"}
          </button>
        </div>
      </form>
    </div>
  </div>;
}
