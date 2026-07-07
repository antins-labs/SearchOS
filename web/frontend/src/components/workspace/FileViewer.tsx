"use client";

import { useEffect, useState } from "react";
import { getFileContent } from "@/lib/api";
import { X, Copy, Check } from "lucide-react";

interface Props {
  sessionId: string;
  filePath: string;
  onClose: () => void;
}

export default function FileViewer({ sessionId, filePath, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setContent(null);
    getFileContent(sessionId, filePath)
      .then((r) => setContent(r.content))
      .catch((e) => setContent(`Error: ${e.message}`));
  }, [sessionId, filePath]);

  const isJson = filePath.endsWith(".json") || filePath.endsWith(".jsonl");
  const formatted = isJson && content ? tryFormatJson(content) : content;

  const handleCopy = () => {
    if (content) {
      navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="truncate text-xs font-mono text-ink-dim">{filePath}</span>
        <div className="flex items-center gap-1">
          <button onClick={handleCopy} className="rounded p-1 text-ink-faint hover:text-ink">
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button onClick={onClose} className="rounded p-1 text-ink-faint hover:text-ink">
            <X size={14} />
          </button>
        </div>
      </div>
      <pre className="flex-1 overflow-auto p-3 text-xs font-mono text-ink-dim leading-relaxed whitespace-pre-wrap">
        {content === null ? "Loading..." : formatted}
      </pre>
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
