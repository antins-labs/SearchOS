"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Keep the agent's prose; drop the noise that duplicates the activity panel:
 *  pipe-tables (the coverage map already is the table), a trailing
 *  References/Sources section, and link-dominated citation dumps. */
function cleanAnswer(md: string): string {
  // cut a trailing references/sources/citations section
  md = md.replace(/\n#{1,6}\s*(references|sources|citations|footnotes|url citations)\b[\s\S]*$/i, "\n");
  const out: string[] = [];
  for (const line of md.split("\n")) {
    if (/^\s*\|.*\|\s*$/.test(line)) continue;          // table rows / separators
    if (/^#{1,6}\s+.*\btable\b/i.test(line)) continue;  // "Summary Table" headings
    if (/_default/.test(line)) continue;                // leaked internal table id
    if (/\bdo not fabricate\b/i.test(line)) continue;   // leaked schema warning
    if (/\d+\/\d+ data cells filled/i.test(line)) continue;
    // drop lines that are mostly links (citation dumps) or agent:// refs
    const urls = line.match(/https?:\/\/\S+|agent:\/\/\S+/g) || [];
    if (urls.length) {
      let rest = line;
      urls.forEach((u) => { rest = rest.replace(u, ""); });
      rest = rest.replace(/[[\]()\d.,\s|*-]/g, "");
      if (rest.length < 8) continue;
    }
    out.push(line);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** Pull just the "Direct Answer" section (heading → next heading). Falls back
 *  to the whole text if the report isn't sectioned that way. */
function directAnswer(md: string): string {
  const lines = md.split("\n");
  const start = lines.findIndex((l) => /^#{1,6}\s+.*direct answer/i.test(l));
  if (start === -1) return md;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^#{1,6}\s+/.test(lines[i])) { end = i; break; }
  }
  return lines.slice(start + 1, end).join("\n").trim() || md;
}

export default function Answer({ markdown, directOnly = false }: { markdown: string; directOnly?: boolean }) {
  const clean = cleanAnswer(directOnly ? directAnswer(markdown) : markdown);
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
        }}
      >
        {clean}
      </ReactMarkdown>
    </div>
  );
}
