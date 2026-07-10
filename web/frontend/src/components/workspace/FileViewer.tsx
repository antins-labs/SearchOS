"use client";

import { useEffect, useState } from "react";
import { getFileContent } from "@/lib/api";
import { X, Copy, Check } from "lucide-react";
import AsyncFeedback from "@/components/ui/AsyncFeedback";
import { useSettings } from "@/components/settings/SettingsProvider";

interface Props {
  sessionId: string;
  filePath: string;
  onClose: () => void;
}

export default function FileViewer({ sessionId, filePath, onClose }: Props) {
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "ready"; content: string }
    | { status: "error"; detail: string }
  >({ status: "loading" });
  const [copied, setCopied] = useState(false);
  const [retrySeq, setRetrySeq] = useState(0);
  const { notify } = useSettings();

  useEffect(() => {
    let alive = true;
    getFileContent(sessionId, filePath)
      .then((r) => alive && setState({ status: "ready", content: r.content }))
      .catch((e) => alive && setState({ status: "error", detail: e instanceof Error ? e.message : String(e) }));
    return () => { alive = false; };
  }, [sessionId, filePath, retrySeq]);

  const content = state.status === "ready" ? state.content : null;

  const isJson = filePath.endsWith(".json") || filePath.endsWith(".jsonl");
  const formatted = isJson && content ? tryFormatJson(content) : content;

  const handleCopy = async () => {
    if (content != null) {
      try {
        await navigator.clipboard.writeText(content);
        notify("File content copied", "success");
      } catch (e) {
        notify(`Copy failed: ${e instanceof Error ? e.message : String(e)}. Try selecting the text manually.`);
        return;
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const retry = () => {
    setState({ status: "loading" });
    setRetrySeq((value) => value + 1);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="truncate text-xs font-mono text-ink-dim">{filePath}</span>
        <div className="flex items-center gap-1">
          <button onClick={() => void handleCopy()} aria-label="Copy file content" title="Copy" disabled={state.status !== "ready"} className="rounded p-1 text-ink-faint hover:text-ink disabled:opacity-30">
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button onClick={onClose} aria-label="Close file" title="Close file" className="rounded p-1 text-ink-faint hover:text-ink">
            <X size={14} />
          </button>
        </div>
      </div>
      {state.status === "loading" ? (
        <AsyncFeedback status="loading" message="Loading file content…" />
      ) : state.status === "error" ? (
        <AsyncFeedback status="error" message="Couldn’t load this file" detail={`${state.detail}. Check the workspace and try again.`} onRetry={retry} />
      ) : (
        <pre className="flex-1 overflow-auto whitespace-pre-wrap p-3 font-mono text-xs leading-relaxed text-ink-dim">
          {formatted}
        </pre>
      )}
    </div>
  );
}

function tryFormatJson(text: string): string {
  // Handle JSONL (multiple lines)
  if (text.includes("\n{")) {
    return text
      .trim()
      .split("\n")
      .map((line) => {
        try {
          return JSON.stringify(JSON.parse(line), null, 2);
        } catch {
          return line;
        }
      })
      .join("\n---\n");
  }
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}
