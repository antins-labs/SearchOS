"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";

import useDialogFocus from "@/hooks/useDialogFocus";
import { getFileContent } from "@/lib/api";
import { highlightCode } from "@/lib/codeHighlight";
import { isCodeTool, parseExecArgs, summarizeExecResult } from "@/lib/execPreview";
import { prettyToolPayload } from "@/lib/tableCursor";

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

type CopyKind = "arguments" | "output" | "code" | "stdout" | "stderr" | "raw";
type CodeTab = "code" | "stdout" | "stderr" | "raw";

function PayloadPane({
  title,
  value,
  copied,
  onCopy,
  pending = false,
  meta,
  highlight = false,
}: {
  title: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
  pending?: boolean;
  meta?: string;
  highlight?: boolean;
}) {
  const body = pending && !value
    ? "工具执行中，结果尚未返回…"
    : highlight
      ? highlightCode(value || "")
      : prettyToolPayload(value);
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col border-b border-line last:border-b-0 md:basis-1/2 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="min-w-0">
          <h3 className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">{title}</h3>
          {meta && <p className="truncate text-[10px] text-ink-faint">{meta}</p>}
        </div>
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
      <pre className="min-h-[160px] max-h-[min(520px,60dvh)] max-w-full flex-1 overflow-auto whitespace-pre-wrap break-all p-4 font-mono text-[11px] leading-5 text-ink">
        {body}
      </pre>
    </section>
  );
}

function StatusDot({ status }: { status?: ToolCallDetail["status"] }) {
  const tone = status === "error" || status === "cancelled" ? "bg-err"
    : status === "running" ? "bg-accent"
      : status === "completed" ? "bg-ok"
        : "bg-ink-faint";
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${tone}`} />;
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
  const [copied, setCopied] = useState<CopyKind | null>(null);
  const [tab, setTab] = useState<CodeTab>("code");
  const [stdout, setStdout] = useState<string | null>(null);
  const [stderr, setStderr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useDialogFocus({
    containerRef: dialogRef,
    initialFocusRef: closeRef,
    onClose,
    active: detail != null,
  });

  useEffect(() => {
    setTab("code");
    setStdout(null);
    setStderr(null);
    setLoadError("");
    setCopied(null);
  }, [detail?.tool, detail?.executionId, detail?.arguments, detail?.output]);

  if (!detail) return null;

  const codeMode = isCodeTool(detail);
  const args = parseExecArgs(detail.arguments);
  const summarized = detail.output ? summarizeExecResult(detail.output) : null;
  const codeBody = args.code || (args.commandLine ? `$ ${args.commandLine}` : "");

  const readSaved = async (stream: "stdout" | "stderr") => {
    if (!sessionId || !detail.executionId) return;
    setLoading(true);
    setLoadError("");
    try {
      const file = await getFileContent(sessionId, `skills/executions/${detail.executionId}/${stream}.log`);
      const text = file.content || "（输出为空）";
      if (stream === "stdout") setStdout(text);
      else setStderr(text);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "读取失败");
    } finally {
      setLoading(false);
    }
  };

  const ensureStream = (stream: "stdout" | "stderr") => {
    if (stream === "stdout" && stdout == null) {
      if (detail.executionId && sessionId) void readSaved("stdout");
      else setStdout(summarized?.stdout || detail.output || "");
    }
    if (stream === "stderr" && stderr == null) {
      if (detail.executionId && sessionId) void readSaved("stderr");
      else setStderr(summarized?.stderr || "");
    }
  };

  const copy = async (kind: CopyKind, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied((current) => current === kind ? null : current), 1400);
    } catch {
      setCopied(null);
    }
  };

  const statusLabel = detail.status === "running" ? "执行中"
    : detail.status === "error" ? "失败"
      : detail.status === "cancelled" ? "已取消"
        : detail.status === "completed" ? "已完成"
          : "";

  return createPortal(
    <div className="fade-in fixed inset-0 z-[80] flex items-center justify-center bg-ink/25 p-3 dark:bg-black/60" onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tool-call-detail-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
        className="surface rise-in flex max-h-[85dvh] w-[min(980px,96vw)] flex-col overflow-hidden rounded-xl shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-ink-faint">
              <StatusDot status={detail.status} />
              <span>{detail.kind === "skill" ? "技能执行 · Exec 子步骤" : codeMode ? "Exec" : "Tool call"}</span>
              {statusLabel && <span className="normal-case tracking-normal text-ink-dim">· {statusLabel}</span>}
            </div>
            <h2 id="tool-call-detail-title" className="mt-0.5 truncate font-mono text-[14px] font-semibold text-ink">{detail.tool}</h2>
            {summarized && <p className="mt-0.5 truncate font-mono text-[11px] text-ink-faint">{summarized.metaLine}</p>}
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

        {codeMode ? (
          <>
            <div className="flex flex-wrap items-center gap-1 border-b border-line px-3 py-2">
              {([
                ["code", "Code"],
                ["stdout", "stdout"],
                ["stderr", "stderr"],
                ["raw", "Raw"],
              ] as const).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => {
                    setTab(id);
                    if (id === "stdout" || id === "stderr") ensureStream(id);
                  }}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium ${
                    tab === id ? "bg-accent/12 text-accent-ink" : "text-ink-dim hover:bg-surface-2"
                  }`}
                >
                  {label}
                </button>
              ))}
              {loading && <span className="ml-2 text-[11px] text-ink-faint">读取中…</span>}
              {loadError && <span role="alert" className="ml-2 text-[11px] text-err">{loadError}</span>}
            </div>
            <div className="flex min-h-0 flex-1 flex-col">
              {tab === "code" && (
                <PayloadPane
                  title="Code"
                  value={codeBody || detail.arguments}
                  meta={codeBody ? `${codeBody.length.toLocaleString()} chars` : undefined}
                  copied={copied === "code"}
                  onCopy={() => void copy("code", codeBody || detail.arguments)}
                  highlight={Boolean(codeBody)}
                />
              )}
              {tab === "stdout" && (
                <PayloadPane
                  title="stdout"
                  value={stdout ?? summarized?.stdout ?? ""}
                  pending={detail.status === "running"}
                  meta={(stdout ?? summarized?.stdout)?.length ? `${(stdout ?? summarized?.stdout ?? "").length.toLocaleString()} chars` : undefined}
                  copied={copied === "stdout"}
                  onCopy={() => void copy("stdout", stdout ?? summarized?.stdout ?? "")}
                />
              )}
              {tab === "stderr" && (
                <PayloadPane
                  title="stderr"
                  value={stderr ?? summarized?.stderr ?? ""}
                  meta={(stderr ?? summarized?.stderr)?.length ? `${(stderr ?? summarized?.stderr ?? "").length.toLocaleString()} chars` : undefined}
                  copied={copied === "stderr"}
                  onCopy={() => void copy("stderr", stderr ?? summarized?.stderr ?? "")}
                />
              )}
              {tab === "raw" && (
                <div className="flex min-h-0 flex-1 flex-col md:flex-row">
                  <PayloadPane
                    title="Parameters"
                    value={detail.arguments}
                    meta={`${detail.arguments.length.toLocaleString()} chars`}
                    copied={copied === "arguments"}
                    onCopy={() => void copy("arguments", detail.arguments)}
                  />
                  <PayloadPane
                    title="Output"
                    value={detail.output}
                    pending={detail.status === "running"}
                    meta={detail.output ? `${detail.output.length.toLocaleString()} chars` : undefined}
                    copied={copied === "raw"}
                    onCopy={() => void copy("raw", detail.output)}
                  />
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <PayloadPane
              title="Parameters"
              value={detail.arguments}
              meta={`${detail.arguments.length.toLocaleString()} chars`}
              copied={copied === "arguments"}
              onCopy={() => void copy("arguments", detail.arguments)}
            />
            <PayloadPane
              title="Output"
              value={detail.output}
              pending={detail.status === "running"}
              meta={detail.output ? `${detail.output.length.toLocaleString()} chars` : undefined}
              copied={copied === "output"}
              onCopy={() => void copy("output", detail.output)}
            />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
