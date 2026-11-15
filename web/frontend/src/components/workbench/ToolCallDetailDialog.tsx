"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";

import useDialogFocus from "@/hooks/useDialogFocus";
import { getFileContent } from "@/lib/api";

export interface ToolCallDetail {
  tool: string;
  arguments: string;
  output: string;
  agent?: string;
  timestamp?: string;
  status?: "running" | "completed" | "error" | "cancelled";
  kind?: "skill";
  executionId?: string;
}

function prettyPayload(value: string): string {
  if (!value.trim()) return "No data recorded";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

function PayloadPane({
  title,
  value,
  copied,
  onCopy,
  pending = false,
}: {
  title: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  pending?: boolean;
}) {
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col border-b border-line last:border-b-0 md:basis-1/2 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">{title}</h3>
        <button
          type="button"
          onClick={onCopy}
          title={`Copy ${title.toLowerCase()}`}
          aria-label={`Copy ${title.toLowerCase()}`}
          className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink"
        >
          {copied ? <Check className="text-ok" size={13} /> : <Copy size={13} />}
        </button>
      </div>
      <pre className="min-h-[180px] max-w-full flex-1 overflow-auto whitespace-pre-wrap break-all p-4 font-mono text-[11px] leading-5 text-ink-dim">
        {pending && !value ? "工具执行中，结果尚未返回…" : prettyPayload(value)}
      </pre>
    </section>
  );
}

export default function ToolCallDetailDialog({
  detail,
  onClose,
  sessionId,
}: {
  detail: ToolCallDetail | null;
  onClose: () => void;
  sessionId?: string | null;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState<"arguments" | "output" | null>(null);
  const [savedOutput, setSavedOutput] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useDialogFocus({
    containerRef: dialogRef,
    initialFocusRef: closeRef,
    onClose,
    active: detail != null,
  });

  if (!detail) return null;

  const readSaved = async (stream: "stdout" | "stderr") => {
    if (!sessionId || !detail.executionId) return;
    setLoading(true);
    setLoadError("");
    try {
      const file = await getFileContent(sessionId, `skills/executions/${detail.executionId}/${stream}.log`);
      setSavedOutput(file.content || "（输出为空）");
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "读取失败");
    } finally {
      setLoading(false);
    }
  };
  const output = savedOutput ?? detail.output;

  const copy = async (kind: "arguments" | "output", value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied((current) => current === kind ? null : current), 1400);
    } catch {
      setCopied(null);
    }
  };

  return createPortal(
    <div className="fade-in fixed inset-0 z-[80] flex items-center justify-center bg-ink/25 p-3 dark:bg-black/60" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tool-call-detail-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
        className="surface rise-in flex h-[min(760px,92dvh)] w-[min(980px,96vw)] flex-col overflow-hidden rounded-xl shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-medium uppercase tracking-wider text-ink-faint">{detail.kind === "skill" ? "技能执行 · Exec 子步骤" : "Tool call"}</div>
            <h2 id="tool-call-detail-title" className="mt-0.5 truncate font-mono text-[14px] font-semibold text-ink">{detail.tool}</h2>
          </div>
          <div className="hidden min-w-0 text-right text-[10.5px] text-ink-faint sm:block">
            {detail.agent && <div>{detail.agent}</div>}
            {detail.timestamp && <div>{detail.timestamp}</div>}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close tool call details"
            className="rounded-md p-1.5 text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <X size={16} />
          </button>
        </div>

        {detail.executionId && sessionId && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2 text-xs">
            {(["stdout", "stderr"] as const).map(stream => (
              <button key={stream} type="button" disabled={loading || detail.status === "running"}
                onClick={() => void readSaved(stream)} className="text-accent-ink underline disabled:opacity-50">
                读取保存的 {stream}
              </button>
            ))}
            {savedOutput != null && <button type="button" onClick={() => setSavedOutput(null)} className="text-ink-dim underline">返回回执预览</button>}
            {loading && <span>读取中…</span>}
            {loadError && <span role="alert" className="text-err">{loadError}</span>}
          </div>
        )}
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <PayloadPane
            title="Parameters"
            value={detail.arguments}
            copied={copied === "arguments"}
            onCopy={() => void copy("arguments", detail.arguments)}
          />
          <PayloadPane
            title="Output"
            value={output}
            pending={detail.status === "running"}
            copied={copied === "output"}
            onCopy={() => void copy("output", output)}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
