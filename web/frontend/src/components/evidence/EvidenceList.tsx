"use client";

import type { EvidenceNode } from "@/lib/types";
import { ExternalLink } from "lucide-react";

interface Props {
  nodes: EvidenceNode[];
}

const ALIGNMENT_STYLE: Record<string, string> = {
  full: "border-ok/40 bg-ok/10 text-ok",
  partial: "border-warn/40 bg-warn/10 text-warn",
  loose: "border-line bg-surface-2 text-ink-dim",
};

export default function EvidenceList({ nodes }: Props) {
  if (!nodes.length) {
    return <div className="p-4 text-sm text-ink-faint">No evidence collected yet.</div>;
  }

  return (
    <div className="space-y-2 p-4">
      <h3 className="text-sm font-medium text-ink">
        Evidence ({nodes.length})
      </h3>
      {nodes.map((n) => {
        const confColor =
          n.confidence >= 0.8 ? "bg-ok" : n.confidence >= 0.5 ? "bg-accent" : "bg-err";
        const alignStyle = n.alignment ? ALIGNMENT_STYLE[n.alignment] : "";
        return (
          <div key={n.id} className="rounded-lg border border-line bg-surface-2 p-3">
            <div className="flex items-start gap-2">
              <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${confColor}`} />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink leading-relaxed">{n.claim}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-dim">
                  {n.table_id && (
                    <span className="rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-ink-dim">
                      {n.table_id}
                    </span>
                  )}
                  {n.entity && <span>{n.entity}.{n.attribute}</span>}
                  {n.alignment && (
                    <span
                      className={`rounded border px-1.5 py-0.5 ${alignStyle}`}
                      title={n.alignment_note || undefined}
                    >
                      {n.alignment}
                    </span>
                  )}
                  <span>{(n.confidence * 100).toFixed(0)}%</span>
                  {n.source && (
                    <a
                      href={n.source}
                      target="_blank"
                      rel="noopener"
                      className="flex items-center gap-1 text-blue-500 hover:underline truncate max-w-[200px] dark:text-blue-400"
                    >
                      <ExternalLink size={10} />
                      {new URL(n.source).hostname}
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
