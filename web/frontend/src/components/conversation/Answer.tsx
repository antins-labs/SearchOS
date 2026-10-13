"use client";

import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  repairMalformedWebLinks,
  repairLocalCitationLinks,
  remarkLocalCitations,
} from "@/lib/localCitations";

/** Keep prose and reference sections intact; remove leaked harness warnings. */
export function cleanAnswer(md: string): string {
  const out: string[] = [];
  for (const line of md.split("\n")) {
    if (/\bdo not fabricate\b/i.test(line)) continue;   // leaked schema warning
    if (/\d+\/\d+ data cells filled/i.test(line)) continue;
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export default function Answer({ markdown, localSources = [], localSourceLabels = {}, evidenceSources = {}, onOpenLocalSource }: {
  markdown: string;
  localSources?: string[];
  localSourceLabels?: Record<string, string>;
  evidenceSources?: Record<string, string>;
  onOpenLocalSource?: (refId: string) => void;
}) {
  const clean = repairLocalCitationLinks(
    repairMalformedWebLinks(cleanAnswer(markdown)),
    localSources,
  );
  if (!clean) return null;
  const originalEntries = new Map<string, { ref: string; label: string }>();
  if (!clean.includes("local://") && !clean.includes("evidence:")) {
    for (const [ref, label] of Object.entries(localSourceLabels)) {
      if (ref.startsWith("local://") && ref.includes("?rev=")) {
        const document = ref.split("?")[0];
        if (!originalEntries.has(document)) originalEntries.set(document, { ref, label });
      }
    }
  }
  return (
    <div className="min-w-0 max-w-full space-y-3 [overflow-wrap:anywhere] text-[15px] leading-[1.7] text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, [remarkLocalCitations, localSourceLabels]]}
        urlTransform={(url) => {
          const source = url.startsWith("evidence:")
            ? evidenceSources[url.slice("evidence:".length)] || "invalid-evidence-reference" : url;
          return source.startsWith("local://") ? source : defaultUrlTransform(source);
        }}
        components={{
          h1: ({ children }) => <h2 className="font-serif text-[22px] font-semibold tracking-tight text-ink">{children}</h2>,
          h2: ({ children }) => <h3 className="mt-4 font-serif text-[18px] font-semibold text-ink">{children}</h3>,
          h3: ({ children }) => <h4 className="mt-3 text-[15px] font-semibold text-ink">{children}</h4>,
          p: ({ children }) => <p>{children}</p>,
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-ink-faint">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 marker:text-ink-faint">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          a: ({ href, children }) => href?.startsWith("local://") ? (
            <button
              type="button"
              onClick={() => onOpenLocalSource?.(href)}
              className="text-left text-accent-ink underline decoration-line-strong underline-offset-2 hover:decoration-accent"
            >
              {children}
            </button>
          ) : href === "invalid-local-reference" || href === "invalid-evidence-reference" ? (
            <span className="text-warn" title="该历史引用无法关联到已验证来源">{children}（来源不可用）</span>
          ) : (
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
      {originalEntries.size > 0 && (
        <div className="space-y-1 border-t border-line pt-3 text-[13px]">
          <p className="text-ink-dim">已读原文入口（全部阅读位置见运行记录）：</p>
          {Array.from(originalEntries.values()).map(({ ref, label }) => (
            <button key={ref} type="button" onClick={() => onOpenLocalSource?.(ref)}
              className="block text-left text-accent-ink underline decoration-line-strong hover:decoration-accent">
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
