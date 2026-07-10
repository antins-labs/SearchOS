"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";

import useDialogFocus from "@/hooks/useDialogFocus";

export interface ToolCallDetail {
  tool: string;
  arguments: string;
  output: string;
  agent?: string;
  timestamp?: string;
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
}: {
  title: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col border-b border-line last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0">
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
      <pre className="min-h-[180px] flex-1 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-[11px] leading-5 text-ink-dim">
        {prettyPayload(value)}
      </pre>
    </section>
  );
}

export default function ToolCallDetailDialog({
  detail,
  onClose,
}: {
  detail: ToolCallDetail | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState<"arguments" | "output" | null>(null);

  useDialogFocus({
    containerRef: dialogRef,
    initialFocusRef: closeRef,
    onClose,
    active: detail != null,
  });

  if (!detail) return null;

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
            <div className="text-[10px] font-medium uppercase tracking-wider text-ink-faint">Tool call</div>
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

        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <PayloadPane
            title="Parameters"
            value={detail.arguments}
            copied={copied === "arguments"}
            onCopy={() => void copy("arguments", detail.arguments)}
          />
          <PayloadPane
            title="Output"
            value={detail.output}
            copied={copied === "output"}
            onCopy={() => void copy("output", detail.output)}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
