"use client";

import { useRef } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, X, Quote } from "lucide-react";
import type { CoverageCell, EvidenceNode } from "@/lib/types";
import useDialogFocus from "@/hooks/useDialogFocus";

export interface CellRef {
  tableId: string;
  entity: string;
  attribute: string;
  cell: CoverageCell;
}

const norm = (s: string) => s.trim().toLowerCase();

/** A source field may hold several comma/space-joined URLs in one string. */
function extractUrls(s: string | string[] | undefined): string[] {
  const joined = Array.isArray(s) ? s.join(" ") : s ?? "";
  return joined.match(/https?:\/\/[^\s,]+/g) ?? [];
}

/** Strip scraper metadata (Jina-reader style "Title: … URL Source: … Markdown
 *  Content:" preamble) and embedded URLs so only real page text remains. */
function cleanExcerpt(raw: string): string {
  let s = raw.replace(/\s+/g, " ").trim();
  // Body text follows the "Markdown Content:" label — everything before it is
  // scraper preamble (title/url/date) that never matches the live page text.
  const body = s.split(/\bMarkdown Content:\s*/i)[1];
  if (body) s = body;
  s = s.replace(/\bURL Source:\s*\S+/gi, " ");
  s = s.replace(/\bPublished Time:\s*\S+/gi, " ");
  s = s.replace(/\b(Markdown Content|Title):\s*/gi, " ");
  s = s.replace(/https?:\/\/\S+/g, " ");
  return s.replace(/\s{2,}/g, " ").trim();
}

/** Evidence nodes bound to one cell — matched on (table_id, entity, attribute),
 *  falling back to source-URL overlap for older states without table ids. */
export function evidenceForCell(nodes: EvidenceNode[], ref: CellRef): EvidenceNode[] {
  const exact = nodes.filter(
    (n) =>
      (!n.table_id || !ref.tableId || n.table_id === ref.tableId) &&
      norm(n.entity || "") === norm(ref.entity) &&
      norm(n.attribute || "") === norm(ref.attribute),
  );
  if (exact.length) return exact;
  const cellUrls = new Set(extractUrls(ref.cell.source));
  if (!cellUrls.size) return [];
  return nodes.filter(
    (n) =>
      norm(n.entity || "") === norm(ref.entity) &&
      extractUrls(n.source).some((u) => cellUrls.has(u)),
  );
}

/** Deep link into the source page: a Text Fragment (#:~:text=…) scrolls to and
 *  highlights the excerpt. Keep the fragment short — exact match required. */
function anchorUrl(url: string, excerpt?: string): string {
  if (!/^https?:\/\//.test(url)) return url;
  const text = cleanExcerpt(excerpt ?? "");
  if (!text) return url;
  // First sentence-ish chunk, capped — long fragments fail to match.
  const chunk = text.split(/(?<=[.!?。！？])\s*/)[0]?.slice(0, 80) || text.slice(0, 80);
  return `${url}#:~:text=${encodeURIComponent(chunk)}`;
}

function hostname(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

const ALIGNMENT_STYLE: Record<string, string> = {
  full: "bg-ok/10 text-ok",
  partial: "bg-warn/10 text-warn",
  loose: "bg-surface-2 text-ink-dim",
};

export default function CellEvidencePopover({
  cellRef,
  nodes,
  onClose,
}: {
  cellRef: CellRef;
  nodes: EvidenceNode[];
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogFocus({ containerRef: dialogRef, initialFocusRef: closeRef, onClose });

  const matched = evidenceForCell(nodes, cellRef);
  const { cell } = cellRef;
  const values = Array.isArray(cell.value) ? cell.value : [cell.value];
  const cellUrls = extractUrls(cell.source);
  const cellPlainSources = (Array.isArray(cell.source) ? cell.source : [cell.source])
    .filter((s): s is string => !!s && !/^https?:\/\//.test(String(s)));

  return createPortal(
    <div className="fade-in fixed inset-0 z-[80] flex items-center justify-center bg-ink/20 p-4 dark:bg-black/50"
      onMouseDown={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cell-evidence-title"
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
        className="rise-in surface flex max-h-[min(560px,85vh)] w-[min(560px,94vw)] flex-col overflow-hidden rounded-2xl shadow-xl"
      >
        {/* header */}
        <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            <div id="cell-evidence-title" className="text-[11px] uppercase tracking-wider text-ink-dim">
              {cellRef.entity.replace(/\|/g, " / ")} · {cellRef.attribute}
            </div>
            <div className="mt-0.5 truncate text-[14px] font-medium text-ink" title={values.join("; ")}>
              {values.join("; ")}
            </div>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close cell evidence"
            className="shrink-0 rounded-md p-1.5 text-ink-dim transition-colors hover:bg-surface-2 hover:text-ink">
            <X size={15} />
          </button>
        </div>

        {/* evidence list */}
        <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-4">
          {matched.length === 0 ? (
            <div className="text-[13px] text-ink-faint">
              No evidence nodes recorded for this cell.
              {(cellUrls.length > 0 || cellPlainSources.length > 0) && (
                <div className="mt-2 space-y-1">
                  {cellUrls.map((u) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer"
                      className="flex items-center gap-1 text-accent-ink hover:underline">
                      <ExternalLink size={12} /> {hostname(u)}
                    </a>
                  ))}
                  {cellPlainSources.map((s, i) => (
                    <div key={i} className="text-ink-dim">{s}</div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            matched.map((n) => {
              const urls = extractUrls(n.source);
              const excerpt = n.source_excerpt ? cleanExcerpt(n.source_excerpt) : "";
              return (
                <div key={n.id} className="rounded-xl border border-line bg-paper/50 p-3">
                  <p className="text-[13.5px] leading-relaxed text-ink">{n.claim}</p>
                  {excerpt && (
                    <blockquote className="mt-2 flex gap-1.5 border-l-2 border-line-strong pl-2.5 text-[12.5px] italic leading-relaxed text-ink-dim">
                      <Quote size={11} className="mt-1 shrink-0 text-ink-faint" />
                      <span className="line-clamp-4">{excerpt}</span>
                    </blockquote>
                  )}
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-ink-dim">
                    {n.alignment && (
                      <span className={`rounded-full px-1.5 py-0.5 capitalize ${ALIGNMENT_STYLE[n.alignment] ?? ALIGNMENT_STYLE.loose}`}
                        title={n.alignment_note || undefined}>
                        {n.alignment}
                      </span>
                    )}
                    <span>confidence {(n.confidence * 100).toFixed(0)}%</span>
                    {urls.length > 0 ? (
                      <span className="ml-auto flex flex-wrap items-center gap-x-2.5 gap-y-1">
                        {urls.map((u, i) => (
                          <a
                            key={u}
                            // The excerpt belongs to one page; anchor only the
                            // primary link — extra sources open plain.
                            href={i === 0 ? anchorUrl(u, n.source_excerpt) : u}
                            target="_blank"
                            rel="noreferrer"
                            title={i === 0 ? "Open the source scrolled to this excerpt" : undefined}
                            className="flex items-center gap-1 font-medium text-accent-ink hover:underline"
                          >
                            <ExternalLink size={12} />
                            {hostname(u)}
                          </a>
                        ))}
                      </span>
                    ) : (
                      n.source && <span className="ml-auto">{n.source}</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
