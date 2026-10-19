"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, Ban, Check, ChevronDown, FileText, FileUp, Globe2, Loader2, Paperclip, RotateCcw, ScanText, Search } from "lucide-react";

import type { LocalLibraryController } from "@/hooks/useLocalLibrary";

function bytesLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

interface Props {
  controller: LocalLibraryController;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function LocalSourceControl({ controller, open, onOpenChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const [filter, setFilter] = useState("");
  const selectedCount = controller.selectedDocumentIds.length;
  const searchableDocuments = useMemo(
    () => controller.documents.filter((document) => document.searchable),
    [controller.documents],
  );
  const filteredDocuments = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    return query
      ? controller.documents.filter((document) => document.name.toLocaleLowerCase().includes(query))
      : controller.documents;
  }, [controller.documents, filter]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) onOpenChange(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
        toggleRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onOpenChange, open]);

  useEffect(() => {
    if (controller.mode === "web") onOpenChange(false);
  }, [controller.mode, onOpenChange]);

  const chooseMode = (mode: "web" | "local" | "hybrid") => {
    controller.setMode(mode);
    onOpenChange(mode !== "web");
  };

  return (
    <div ref={rootRef} className="mb-2 text-[12px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="flex rounded-lg border border-line bg-surface p-0.5">
          <button
            type="button"
            aria-pressed={controller.mode === "web"}
            onClick={() => chooseMode("web")}
            className={`flex items-center gap-1 rounded-md px-2 py-1 transition-colors ${controller.mode === "web" ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"}`}
          >
            <Globe2 size={12} />Web
          </button>
          <button
            type="button"
            aria-pressed={controller.mode === "local"}
            onClick={() => chooseMode("local")}
            className={`flex items-center gap-1 rounded-md px-2 py-1 transition-colors ${controller.mode === "local" ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"}`}
          >
            <Search size={12} />Local
          </button>
          <button
            type="button"
            aria-pressed={controller.mode === "hybrid"}
            onClick={() => chooseMode("hybrid")}
            className={`flex items-center gap-1 rounded-md px-2 py-1 transition-colors ${controller.mode === "hybrid" ? "bg-clay text-accent-ink" : "text-ink-faint hover:text-ink-dim"}`}
          >
            <Globe2 size={12} />Hybrid
          </button>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={controller.uploading}
          className="flex items-center gap-1 rounded-lg border border-line bg-surface px-2 py-1 text-ink-dim transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
        >
          {controller.uploading ? <Loader2 className="animate-spin" size={12} /> : <Paperclip size={12} />}
          添加文件
        </button>
        <input
          ref={inputRef}
          className="hidden"
          type="file"
          multiple
          accept=".md,.markdown,.txt,.pdf,.docx,.pptx,.xlsx,.csv,.tsv,.json,.jsonl,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            if (files.length > 0) {
              if (controller.mode === "web") controller.setMode("local");
              onOpenChange(true);
            }
            void controller.uploadFiles(files);
          }}
        />
        {controller.mode !== "web" && (
          <button
            ref={toggleRef}
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => onOpenChange(!open)}
            title={selectedCount ? controller.documents.filter((document) => controller.selectedDocumentIds.includes(document.document_id)).map((document) => document.name).join("\n") : undefined}
            className="flex min-w-0 items-center gap-1 rounded-lg px-2 py-1 text-ink-dim hover:bg-surface-2"
          >
            <FileText size={12} />
            <span>{selectedCount > 0 ? `已选 ${selectedCount} 份` : "选择资料"}</span>
            <ChevronDown className={`transition-transform ${open ? "rotate-180" : ""}`} size={12} />
          </button>
        )}
        {controller.mode !== "web" && (
          <span className="text-ink-faint">{selectedCount > 0 ? "仅检索所选文档" : controller.libraryId ? "按问题检索当前知识库" : "暂无本地知识库"}</span>
        )}
      </div>

      {controller.mode === "hybrid" && (
        <p className="mt-1.5 text-ink-faint">自主安排本地探索与联网检索；未选文档时可探索当前知识库，选择文档可限定范围。</p>
      )}
      {controller.mode === "local" && selectedCount === 0 && !open && (
        <p className="mt-1.5 text-ink-faint">未选文档时检索整个当前知识库；选择文档可限定问答范围。</p>
      )}
      {controller.mode !== "web" && open && (
        <div id={panelId} aria-label="选择本地资料" className="surface rise-in mt-2 max-h-80 overflow-y-auto rounded-xl p-2.5 shadow-lg">
          {controller.uploads.length > 0 && (
            <section className="mb-2 rounded-lg border border-line bg-paper/60 p-2" aria-label="上传与后台索引任务">
              <div className="mb-1.5 flex items-center justify-between gap-2 px-1">
                <span className="font-medium text-ink">上传与后台索引</span>
                {controller.uploading && <span className="text-ink-faint">解析完成即可问答</span>}
              </div>
              <div className="space-y-1.5">
                {controller.uploads.slice(0, 6).map((item) => {
                  const active = item.status === "uploading" || item.status === "parsing" || item.status === "indexing";
                  const statusLabel = item.status === "queued"
                    ? "等待上传"
                    : item.status === "uploading"
                    ? `上传 ${item.progress}%`
                    : item.status === "parsing"
                      ? "正在解析正文"
                      : item.status === "indexing"
                        ? "可问答 · 后台生成 Recap/目录"
                      : item.status === "ready"
                        ? item.cached ? "可问答 · 已复用索引" : "可问答 · 索引完成"
                        : item.status === "index_error"
                          ? "可问答 · 后台索引失败"
                          : item.status === "index_cancelled"
                            ? "可问答 · 后台索引已取消"
                          : "上传或解析失败";
                  return (
                    <div key={item.id} className="rounded-md bg-surface px-2 py-1.5">
                      <div className="flex items-center gap-2">
                        <span className={item.status === "error" ? "text-err" : item.status === "index_error" ? "text-warn" : item.status === "ready" ? "text-ok" : "text-accent-ink"}>
                          {item.status === "queued" ? <Paperclip size={13} /> : item.status === "uploading" ? <FileUp size={13} /> : item.status === "parsing" || item.status === "indexing" ? <ScanText size={13} /> : item.status === "ready" ? <Check size={13} /> : <AlertTriangle size={13} />}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-ink" title={item.name}>{item.name}</span>
                        <span className="shrink-0 text-ink-faint">{bytesLabel(item.sizeBytes)}</span>
                        <span className={`shrink-0 ${item.status === "error" ? "text-err" : item.status === "index_error" ? "text-warn" : item.status === "ready" ? "text-ok" : "text-ink-dim"}`}>{statusLabel}</span>
                        {active && <Loader2 className="shrink-0 animate-spin text-accent-ink" size={12} />}
                      </div>
                      {active && (
                        <div
                          role="progressbar"
                          aria-label={`${item.name} ${statusLabel}`}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-valuenow={item.status === "uploading" ? item.progress : undefined}
                          className="mt-1.5 h-1 overflow-hidden rounded-full bg-line"
                        >
                          <div className={`h-full rounded-full bg-accent transition-[width] ${item.status === "parsing" || item.status === "indexing" ? "w-full animate-pulse" : ""}`} style={item.status === "uploading" ? { width: `${item.progress}%` } : undefined} />
                        </div>
                      )}
                      {item.error && <p className="mt-1 break-words text-[11px] text-err">{item.error}</p>}
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          {controller.libraries.length > 0 && (
            <select
              value={controller.libraryId ?? ""}
              onChange={(event) => {
                setFilter("");
                controller.setLibraryId(event.target.value);
              }}
              className="input-surface mb-2 w-full rounded-lg border border-line bg-surface-2 px-2.5 py-1.5 text-[12px] text-ink outline-none"
            >
              {controller.libraries.map((library) => (
                <option key={library.library_id} value={library.library_id}>{library.name}</option>
              ))}
            </select>
          )}
          {controller.documents.length > 0 && (
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <label className="input-surface flex min-w-44 flex-1 items-center gap-1.5 rounded-lg border border-line bg-paper px-2 py-1.5">
                <Search size={12} className="shrink-0 text-ink-faint" />
                <input
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="搜索资料"
                  className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-faint"
                />
              </label>
              <span className="text-ink-faint">{selectedCount}/{searchableDocuments.length}</span>
              <button
                type="button"
                disabled={searchableDocuments.length === 0 || searchableDocuments.every((document) => controller.selectedDocumentIds.includes(document.document_id))}
                onClick={() => searchableDocuments.forEach((document) => controller.setDocumentSelected(document.document_id, true))}
                className="rounded-md px-1.5 py-1 text-accent-ink hover:bg-clay disabled:opacity-35"
              >全选可用</button>
              <button
                type="button"
                disabled={selectedCount === 0}
                onClick={() => controller.selectedDocumentIds.forEach((documentId) => controller.setDocumentSelected(documentId, false))}
                className="rounded-md px-1.5 py-1 text-ink-faint hover:bg-surface-2 hover:text-ink disabled:opacity-35"
              >清空</button>
            </div>
          )}
          {controller.loading && controller.documents.length === 0 ? (
            <div className="flex items-center gap-2 px-1 py-3 text-ink-faint"><Loader2 className="animate-spin" size={13} />读取资料…</div>
          ) : controller.documents.length === 0 ? (
            <button type="button" onClick={() => inputRef.current?.click()} className="w-full rounded-lg border border-dashed border-line px-3 py-5 text-center text-ink-faint hover:text-ink-dim">
              还没有资料，添加一份文档
            </button>
          ) : filteredDocuments.length === 0 ? (
            <div className="rounded-lg border border-dashed border-line px-3 py-5 text-center text-ink-faint">
              没有匹配的资料
            </div>
          ) : (
            <div className="space-y-1">
              {filteredDocuments.map((document) => {
                const selected = controller.selectedDocumentIds.includes(document.document_id);
                const jobStatus = document.index_job?.status;
                const documentStatus = !document.searchable
                  ? document.parse_status === "failed"
                    ? "解析失败"
                    : document.parse_status === "pending"
                      ? "已保存 · 未索引"
                      : "部分可用"
                  : jobStatus === "queued" || jobStatus === "running"
                    ? "可问答 · 索引中"
                    : jobStatus === "failed"
                      ? "可问答 · 索引失败"
                      : jobStatus === "cancelled"
                        ? "可问答 · 索引已取消"
                      : document.catalog_status === "ready"
                        ? "可问答 · 已编目"
                        : "可问答";
                const jobId = document.index_job?.job_id;
                const jobActionPending = Boolean(jobId && controller.jobActionIds.includes(jobId));
                const canCancel = jobStatus === "queued" || jobStatus === "running";
                const canRetry = jobStatus === "failed" || jobStatus === "cancelled";
                return (
                  <div key={document.document_id} className="flex items-center rounded-lg hover:bg-surface-2">
                    <button
                      type="button"
                      aria-pressed={selected}
                      disabled={!document.searchable}
                      onClick={() => controller.setDocumentSelected(document.document_id, !selected)}
                      className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left disabled:opacity-50"
                    >
                      <span className={`grid h-4 w-4 shrink-0 place-items-center rounded border ${selected ? "border-accent bg-accent text-white" : "border-line-strong"}`}>
                        {selected && <Check size={11} />}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-ink">{document.name}</span>
                      <span className={!document.searchable && document.parse_status === "failed" ? "text-err" : jobStatus === "failed" || jobStatus === "cancelled" ? "text-warn" : document.searchable ? "text-ok" : "text-warn"}>
                        {documentStatus}
                      </span>
                      <span className="text-ink-faint">{bytesLabel(document.size_bytes)}</span>
                    </button>
                    {jobId && (canCancel || canRetry) && (
                      <button
                        type="button"
                        disabled={jobActionPending}
                        onClick={() => { void (canCancel ? controller.cancelIndexJob(jobId) : controller.retryIndexJob(jobId)); }}
                        className="mr-1 flex shrink-0 items-center gap-1 rounded-md border border-line px-1.5 py-1 text-[11px] text-ink-dim hover:bg-paper disabled:opacity-50"
                        title={canCancel ? "取消 Recap/目录后台作业" : "重试 Recap/目录后台作业"}
                      >
                        {jobActionPending ? <Loader2 className="animate-spin" size={11} /> : canCancel ? <Ban size={11} /> : <RotateCcw size={11} />}
                        {canCancel ? "取消" : "重试"}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {controller.error && <p role="alert" className="mt-2 rounded-lg bg-err/5 px-2 py-1.5 text-err">{controller.error}</p>}
        </div>
      )}
    </div>
  );
}
