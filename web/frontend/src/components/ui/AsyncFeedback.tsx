"use client";

import { CircleAlert, Loader2, RotateCcw } from "lucide-react";

interface Props {
  status: "loading" | "error";
  message: string;
  detail?: string;
  onRetry?: () => void;
  compact?: boolean;
}

export default function AsyncFeedback({ status, message, detail, onRetry, compact = false }: Props) {
  return (
    <div
      role={status === "error" ? "alert" : "status"}
      aria-live="polite"
      className={`flex min-h-24 items-start gap-3 text-[13px] ${compact ? "p-3" : "p-5"}`}
    >
      {status === "loading" ? (
        <Loader2 className="mt-0.5 shrink-0 animate-spin text-accent-ink" size={17} />
      ) : (
        <CircleAlert className="mt-0.5 shrink-0 text-err" size={17} />
      )}
      <div className="min-w-0">
        <p className={status === "error" ? "text-ink" : "text-ink-dim"}>{message}</p>
        {detail && <p className="mt-1 break-words text-[12px] leading-5 text-ink-faint">{detail}</p>}
        {status === "error" && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-line-strong px-2.5 py-1.5 font-medium text-ink transition-colors hover:bg-surface-2"
          >
            <RotateCcw size={13} />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
