"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, FileText, ListTree, Loader2 } from "lucide-react";

import { getLocalDocumentIndex, getLocalDocumentSegment } from "@/lib/api";
import type { LocalDocumentIndex } from "@/lib/types";

interface Props {
  libraryId: string;
  documentId: string;
}

interface SegmentContent {
  content: string;
  nextOffset: number | null;
  loading: boolean;
  error?: string;
}

export default function DocumentIndexView({ libraryId, documentId }: Props) {
  const [index, setIndex] = useState<LocalDocumentIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSegmentIds, setActiveSegmentIds] = useState<string[]>([]);
  const [contents, setContents] = useState<Record<string, SegmentContent>>({});
  const segmentRefs = useRef(new Map<string, HTMLElement>());

  const loadSegment = useCallback(async (segmentId: string, offset = 0) => {
    const append = offset > 0;
    setContents((current) => {
      const previous = current[segmentId];
      return {
        ...current,
        [segmentId]: {
          content: append ? previous?.content ?? "" : previous?.content ?? "",
          nextOffset: previous?.nextOffset ?? null,
          loading: true,
        },
      };
    });
    try {
      const chunk = await getLocalDocumentSegment(
        libraryId,
        documentId,
        segmentId,
        offset,
      );
      setContents((current) => ({
        ...current,
        [segmentId]: {
          content: append
            ? `${current[segmentId]?.content ?? ""}${chunk.content}`
            : chunk.content,
          nextOffset: chunk.next_offset,
          loading: false,
        },
      }));
    } catch (cause) {
      setContents((current) => ({
        ...current,
        [segmentId]: {
          content: current[segmentId]?.content ?? "",
          nextOffset: current[segmentId]?.nextOffset ?? null,
          loading: false,
          error: cause instanceof Error ? cause.message : String(cause),
        },
      }));
    }
  }, [documentId, libraryId]);

  const reveal = useCallback((segmentIds: string[]) => {
    const target = segmentIds[0];
    if (!target) return;
    setActiveSegmentIds(segmentIds);
    if (!contents[target]?.content && !contents[target]?.loading) {
      void loadSegment(target);
    }
    window.requestAnimationFrame(() => {
      segmentRefs.current.get(target)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [contents, loadSegment]);

  useEffect(() => {
    let alive = true;
    setIndex(null);
    setError(null);
    setContents({});
    setActiveSegmentIds([]);
    void getLocalDocumentIndex(libraryId, documentId)
      .then((value) => {
        if (!alive) return;
        setIndex(value);
        const first = value.outline.find((entry) => entry.segment_ids.length > 0)?.segment_ids
          ?? value.segments.slice(0, 1).map((segment) => segment.segment_id);
        if (first.length > 0) {
          setActiveSegmentIds(first);
          void loadSegment(first[0]);
        }
      })
      .catch((cause) => {
        if (alive) setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => { alive = false; };
  }, [documentId, libraryId, loadSegment]);

  if (error) {
    return <div role="alert" className="grid min-h-0 flex-1 place-items-center p-6 text-[13px] text-err">{error}</div>;
  }
  if (!index) {
    return <div className="grid min-h-0 flex-1 place-items-center text-[13px] text-ink-faint"><span className="flex items-center gap-2"><Loader2 className="animate-spin" size={14} />读取文档索引…</span></div>;
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[320px_minmax(0,1fr)]">
      <nav className="max-h-72 overflow-y-auto border-b border-line bg-surface/60 p-4 md:max-h-none md:border-b-0 md:border-r" aria-label="文档目录索引">
        <div className="mb-3 flex items-center gap-2">
          <ListTree size={15} className="text-accent-ink" />
          <div>
            <h2 className="text-[13px] font-medium text-ink">目录索引</h2>
            <p className="text-[10px] text-ink-faint">{index.outline.length} 项 · 点击定位 segment</p>
          </div>
        </div>
        {index.summary && <p className="mb-3 rounded-lg bg-paper p-2.5 text-[11px] leading-5 text-ink-dim">{index.summary}</p>}
        <div className="space-y-1.5">
          {index.outline.map((entry) => {
            const active = entry.segment_ids.some((id) => activeSegmentIds.includes(id));
            return (
              <button
                key={entry.entry_id}
                type="button"
                disabled={entry.segment_ids.length === 0}
                onClick={() => reveal(entry.segment_ids)}
                className={`w-full rounded-lg border px-2.5 py-2 text-left ${active ? "border-accent bg-clay" : "border-transparent hover:border-line hover:bg-paper"} disabled:cursor-not-allowed disabled:opacity-50`}
              >
                <span className="block text-[12px] font-medium text-ink">{entry.title || entry.location_label}</span>
                <span className="mt-0.5 block text-[10px] text-ink-faint">{entry.location_label} · {entry.character_count.toLocaleString()} chars</span>
                {entry.summary && <span className="mt-1 line-clamp-3 block text-[11px] leading-4 text-ink-dim">{entry.summary}</span>}
              </button>
            );
          })}
        </div>
      </nav>

      <main className="min-h-0 overflow-y-auto bg-paper p-4 sm:p-6" aria-label="文档 segment 内容">
        <div className="mx-auto max-w-4xl space-y-3">
          {index.segments.map((segment) => {
            const value = contents[segment.segment_id];
            const active = activeSegmentIds.includes(segment.segment_id);
            return (
              <article
                key={segment.segment_id}
                ref={(node) => {
                  if (node) segmentRefs.current.set(segment.segment_id, node);
                  else segmentRefs.current.delete(segment.segment_id);
                }}
                id={`local-segment-${encodeURIComponent(segment.segment_id)}`}
                className={`scroll-mt-4 rounded-xl border p-4 transition-colors ${active ? "border-accent bg-clay/30 shadow-sm" : "border-line bg-surface"}`}
              >
                <button type="button" onClick={() => reveal([segment.segment_id])} className="flex w-full items-start gap-2 text-left">
                  <FileText size={14} className="mt-0.5 shrink-0 text-ink-faint" />
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-[13px] font-medium text-ink">{segment.title || segment.location_label}</span>
                    <span className="mt-0.5 block text-[10px] text-ink-faint">{segment.location_label} · {segment.extraction_method} · {segment.character_count.toLocaleString()} chars</span>
                  </span>
                </button>
                {!value && <button type="button" onClick={() => { void loadSegment(segment.segment_id); }} className="mt-3 rounded-lg border border-line px-2.5 py-1.5 text-[11px] text-ink-dim hover:bg-surface-2">加载内容</button>}
                {value?.loading && !value.content && <div className="mt-3 flex items-center gap-2 text-[11px] text-ink-faint"><Loader2 className="animate-spin" size={12} />加载 segment…</div>}
                {value?.error && <div role="alert" className="mt-3 text-[11px] text-err">{value.error}</div>}
                {value?.content && <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-[12px] leading-6 text-ink-dim">{value.content}</pre>}
                {value?.nextOffset !== null && value?.nextOffset !== undefined && (
                  <button type="button" disabled={value.loading} onClick={() => { void loadSegment(segment.segment_id, value.nextOffset ?? 0); }} className="mt-3 flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[11px] text-ink-dim hover:bg-surface-2 disabled:opacity-40">
                    {value.loading ? <Loader2 className="animate-spin" size={12} /> : <ChevronDown size={12} />}加载更多
                  </button>
                )}
              </article>
            );
          })}
          {index.segments.length === 0 && <div className="py-12 text-center text-[13px] text-ink-faint">该文档没有可展示的文本 segment</div>}
        </div>
      </main>
    </div>
  );
}
