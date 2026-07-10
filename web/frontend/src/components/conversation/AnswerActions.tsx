"use client";

import { ChevronDown, ChevronUp, Copy, CornerDownRight, Download, RotateCcw } from "lucide-react";
import { useSettings } from "@/components/settings/SettingsProvider";

interface Props {
  query: string;
  markdown: string;
  collapsible: boolean;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onRerun: () => void;
  onContinue?: () => void;
  runDisabled?: boolean;
}

const buttonClass = "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink active:bg-clay disabled:cursor-not-allowed disabled:opacity-30";

function markdownFilename(query: string): string {
  const stem = query
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 64)
    .replace(/^-+|-+$/g, "");
  return `${stem || "searchos-answer"}.md`;
}

export default function AnswerActions({
  query,
  markdown,
  collapsible,
  collapsed,
  onToggleCollapse,
  onRerun,
  onContinue,
  runDisabled = false,
}: Props) {
  const { notify } = useSettings();

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      notify("Answer copied", "success");
    } catch (error) {
      notify(`Couldn’t copy the answer: ${error instanceof Error ? error.message : String(error)}. Try selecting the text manually.`);
    }
  };

  const downloadMarkdown = () => {
    try {
      const content = `# ${query}\n\n${markdown.trim()}\n`;
      const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = markdownFilename(query);
      anchor.style.display = "none";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      globalThis.setTimeout(() => URL.revokeObjectURL(url), 1000);
      notify("Markdown download started", "success");
    } catch (error) {
      notify(`Couldn’t export Markdown: ${error instanceof Error ? error.message : String(error)}. Try copying the answer instead.`);
    }
  };

  return (
    <div role="toolbar" aria-label="Answer actions" className="mt-2 flex min-h-8 items-center gap-0.5 border-t border-line pt-2">
      <button type="button" onClick={() => void copyAnswer()} aria-label="Copy answer" title="Copy answer" className={buttonClass}>
        <Copy size={15} />
      </button>
      <button type="button" onClick={downloadMarkdown} aria-label="Download Markdown" title="Download Markdown" className={buttonClass}>
        <Download size={15} />
      </button>
      {collapsible && (
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand answer" : "Collapse answer"}
          title={collapsed ? "Expand answer" : "Collapse answer"}
          className={buttonClass}
        >
          {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
      )}
      <span className="mx-1 h-4 w-px bg-line" />
      <button
        type="button"
        onClick={onRerun}
        disabled={runDisabled}
        aria-label="Run this query again"
        title={runDisabled ? "Wait for the active run to finish" : "Run this query again"}
        className={buttonClass}
      >
        <RotateCcw size={15} />
      </button>
      {onContinue && (
        <button
          type="button"
          onClick={onContinue}
          disabled={runDisabled}
          aria-label="Continue from this answer"
          title={runDisabled ? "Wait for the active run to finish" : "Continue from this answer"}
          className={buttonClass}
        >
          <CornerDownRight size={16} />
        </button>
      )}
    </div>
  );
}
