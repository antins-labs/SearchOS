"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileText, ImageIcon, Loader2, X } from "lucide-react";

import useDialogFocus from "@/hooks/useDialogFocus";
import { localOriginalUrl, localPreviewUrl, resolveLocalCitation } from "@/lib/api";
import type { LocalCitation } from "@/lib/types";

export default function SourcePanel({ refId, onClose }: { refId: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [resolved, setResolved] = useState<{
    refId: string;
    citation?: LocalCitation;
    error?: string;
  } | null>(null);
  const [view, setView] = useState<"original" | "excerpt">("original");
  const citation = resolved?.refId === refId ? resolved.citation ?? null : null;
  const error = resolved?.refId === refId ? resolved.error ?? null : null;

  useEffect(() => {
    let alive = true;
    void resolveLocalCitation(refId)
      .then((value) => {
        if (!alive) return;
        setResolved({ refId, citation: value });
        setView(value.preview_mode === "unsupported" ? "excerpt" : "original");
      })
      .catch((cause) => {
        if (alive) setResolved({ refId, error: cause instanceof Error ? cause.message : String(cause) });
      });
    return () => { alive = false; };
  }, [refId]);
  const originalUrl = useMemo(() => citation ? localOriginalUrl(citation) : "", [citation]);
  const previewUrl = useMemo(() => citation ? localPreviewUrl(citation) : "", [citation]);
  useDialogFocus({ containerRef: dialogRef, initialFocusRef: closeRef, onClose });

  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-ink/20 dark:bg-black/50" onMouseDown={onClose}>
      <aside
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="本地原文"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
        className="drawer-in flex h-full w-full max-w-2xl flex-col border-l border-line bg-paper shadow-2xl"
      >
        <header className="flex items-center gap-3 border-b border-line px-4 py-3">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-clay text-accent-ink"><FileText size={16} /></span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold text-ink">{citation?.file_name ?? "读取本地原文"}</div>
            <div className="truncate text-[12px] text-ink-faint">{citation?.location_label ?? "正在校验来源和版本"}</div>
          </div>
          {citation && (
            <a href={originalUrl} target="_blank" rel="noreferrer" className="rounded-lg p-2 text-ink-dim hover:bg-surface-2" title="在新窗口打开原件" aria-label="在新窗口打开原件">
              <ExternalLink size={16} />
            </a>
          )}
          <button ref={closeRef} type="button" onClick={onClose} className="rounded-lg p-2 text-ink-dim hover:bg-surface-2" aria-label="关闭"><X size={17} /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {!citation && !error && <div className="flex items-center gap-2 text-[13px] text-ink-faint"><Loader2 className="animate-spin" size={14} />校验并读取原文…</div>}
          {error && <div role="alert" className="rounded-xl border border-err/30 bg-err/5 px-3 py-2 text-[13px] text-err">{error}</div>}
          {citation && (
            <div className="flex h-full min-h-0 flex-col">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                <span className="rounded-md bg-surface-2 px-2 py-1">Local</span>
                <span className="rounded-md bg-surface-2 px-2 py-1">{citation.representation_id}</span>
                <span className="rounded-md bg-surface-2 px-2 py-1">版本 {citation.source_revision.slice(0, 12)}</span>
                {citation.preview_mode === "office" && <span className="rounded-md bg-surface-2 px-2 py-1">Office→PDF</span>}
                <div className="ml-auto flex rounded-lg border border-line bg-surface-2 p-0.5 text-[12px]">
                  <button type="button" disabled={citation.preview_mode === "unsupported"} onClick={() => setView("original")} className={`rounded-md px-2.5 py-1 ${view === "original" ? "bg-paper text-ink shadow-sm" : "text-ink-faint"} disabled:opacity-40`}>原件预览</button>
                  <button type="button" onClick={() => setView("excerpt")} className={`rounded-md px-2.5 py-1 ${view === "excerpt" ? "bg-paper text-ink shadow-sm" : "text-ink-faint"}`}>提取片段</button>
                </div>
              </div>
              {view === "original" && citation.preview_mode === "image" && (
                <div className="flex min-h-[20rem] flex-1 items-center justify-center overflow-auto rounded-xl border border-line bg-surface p-3">
                  {/* eslint-disable-next-line @next/next/no-img-element -- authenticated local source URL is not an optimizable asset. */}
                  <img src={originalUrl} alt={`${citation.file_name} 原件`} className="max-h-full max-w-full object-contain" />
                </div>
              )}
              {view === "original" && ["pdf", "text", "office"].includes(citation.preview_mode) && (
                <iframe src={previewUrl} title={`${citation.file_name} 原件`} className="min-h-[32rem] flex-1 rounded-xl border border-line bg-white" />
              )}
              {view === "excerpt" && (
                <div className="min-h-0 flex-1 overflow-y-auto">
                  <div className="mb-2 flex items-center gap-1.5 text-[11px] text-ink-faint"><FileText size={12} />解析表示中的命中片段，不等同于完整原件</div>
                  <pre className="whitespace-pre-wrap break-words rounded-xl border border-line bg-surface px-4 py-3 font-sans text-[14px] leading-7 text-ink">{citation.content}</pre>
                </div>
              )}
              {citation.preview_mode === "unsupported" && view === "excerpt" && (
                <a href={originalUrl} target="_blank" rel="noreferrer" className="mt-3 flex items-center justify-center gap-2 rounded-lg border border-line px-3 py-2 text-[12px] text-accent-ink hover:bg-surface-2"><ImageIcon size={14} />打开或下载完整原件</a>
              )}
              {citation.warnings.length > 0 && (
                <div className="mt-3 rounded-lg bg-warn/5 px-3 py-2 text-[12px] text-warn">{citation.warnings.join("；")}</div>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
