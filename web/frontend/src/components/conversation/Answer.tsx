"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Keep the agent's prose intact — the answer must render complete. Only
 *  strip lines that leak harness internals, plus a trailing References dump
 *  (the Evidence tab already lists sources with full URLs). */
export function cleanAnswer(md: string): string {
  // cut a trailing references/sources/citations section
  md = md.replace(/\n#{1,6}\s*(references|sources|citations|footnotes|url citations)\b[\s\S]*$/i, "\n");
  const out: string[] = [];
  for (const line of md.split("\n")) {
    if (/\bdo not fabricate\b/i.test(line)) continue;   // leaked schema warning
    if (/\d+\/\d+ data cells filled/i.test(line)) continue;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export default function Answer({ markdown }: { markdown: string }) {
  const clean = cleanAnswer(markdown);
  if (!clean) return null;
  return (
    <div className="space-y-3 text-[15px] leading-[1.7] text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h2 className="font-serif text-[22px] font-semibold tracking-tight text-ink">{children}</h2>,
          h2: ({ children }) => <h3 className="mt-4 font-serif text-[18px] font-semibold text-ink">{children}</h3>,
          h3: ({ children }) => <h4 className="mt-3 text-[15px] font-semibold text-ink">{children}</h4>,
          p: ({ children }) => <p>{children}</p>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-ink-faint">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 marker:text-ink-faint">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-accent-ink underline decoration-line-strong underline-offset-2 hover:decoration-accent">{children}</a>
          ),
          strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
          code: ({ children }) => <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[13px] text-accent-ink">{children}</code>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-line-strong pl-3 text-ink-dim">{children}</blockquote>,
          hr: () => <hr className="border-line" />,
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full text-[13.5px]">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface-2 text-left">{children}</thead>,
          th: ({ children }) => (
            <th className="whitespace-nowrap border-b border-line px-3 py-2 text-[12.5px] font-medium text-ink-dim">{children}</th>
          ),
          td: ({ children }) => <td className="border-b border-line px-3 py-2 align-top">{children}</td>,
          tr: ({ children }) => <tr className="last:[&>td]:border-b-0">{children}</tr>,
        }}
      >
        {clean}
      </ReactMarkdown>
    </div>
  );
}
