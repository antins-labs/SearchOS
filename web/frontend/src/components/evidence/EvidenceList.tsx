"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ExternalLink,
  GitCompareArrows,
  Link2,
  Loader2,
  Quote,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import type {
  CoverageMap,
  EvidenceEdge,
  EvidenceNode,
  RepairCellTarget,
} from "@/lib/types";

type EvidenceView = "conflicts" | "relations" | "all";

interface Props {
  nodes: EvidenceNode[];
  edges?: EvidenceEdge[];
  coverageMap?: CoverageMap | null;
  onResolve?: (target: RepairCellTarget, evidenceId: string) => Promise<void>;
  onReverify?: (target: RepairCellTarget) => void;
}

interface ConflictGroup {
  key: string;
  target: RepairCellTarget;
  nodes: EvidenceNode[];
  primaryId?: string;
  resolved: boolean;
}

const AUTHORITY_WEIGHT: Record<string, number> = {
  official: 1,
  industry_pr: 0.85,
  aggregator: 0.7,
  news: 0.65,
  blog: 0.5,
  unclear: 0.6,
};

const RELATION_STYLE: Record<EvidenceEdge["relation"], string> = {
  support: "bg-ok/10 text-ok",
  conflict: "bg-err/10 text-err",
  refine: "bg-accent/10 text-accent-ink",
};

function effectiveTable(node: EvidenceNode, primaryTable: string): string {
  return node.table_id || primaryTable;
}

function sourceLabel(source: string): string {
  if (!source) return "Unknown source";
  try { return new URL(source).hostname.replace(/^www\./, ""); } catch { return source; }
}

function cleanExcerpt(raw: string): string {
  let value = raw.replace(/\s+/g, " ").trim();
  const body = value.split(/\bMarkdown Content:\s*/i)[1];
  if (body) value = body;
  return value
    .replace(/\bURL Source:\s*\S+/gi, " ")
    .replace(/\bPublished Time:\s*\S+/gi, " ")
    .replace(/\b(Markdown Content|Title):\s*/gi, " ")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function capturedAt(timestamp?: number): string {
  if (!timestamp) return "Time unavailable";
  return `Captured ${new Date(timestamp * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

function quality(node: EvidenceNode): number {
  if (typeof node.quality_score === "number") return node.quality_score;
  return node.confidence * (AUTHORITY_WEIGHT[node.source_authority || "unclear"] ?? 0.6);
}

function buildConflictGroups(
  nodes: EvidenceNode[],
  edges: EvidenceEdge[],
  coverageMap?: CoverageMap | null,
): ConflictGroup[] {
  const primaryTable = Object.keys(coverageMap?.tables ?? {})[0] ?? "_default";
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const groups = new Map<string, { target: RepairCellTarget; ids: Set<string>; primaryId?: string; cellConflict?: boolean }>();

  for (const [cellKey, cell] of Object.entries(coverageMap?.cells ?? {})) {
    const ids = new Set(cell.conflict_evidence_ids ?? []);
    if (cell.primary_evidence_id) ids.add(cell.primary_evidence_id);
    if (cell.has_conflict && ids.size < 2) {
      for (const id of cell.supporting_evidence_ids ?? []) ids.add(id);
    }
    if (ids.size < 2) continue;
    const [tableId, rest = ""] = cellKey.split("/", 2);
    const dot = rest.lastIndexOf(".");
    if (dot < 0) continue;
    groups.set(cellKey, {
      target: { table_id: tableId, entity: rest.slice(0, dot), attribute: rest.slice(dot + 1) },
      ids,
      primaryId: cell.primary_evidence_id,
      cellConflict: !!cell.has_conflict,
    });
  }

  for (const edge of edges) {
    if (edge.relation !== "conflict") continue;
    const from = byId.get(edge.from_id);
    const to = byId.get(edge.to_id);
    if (!from || !to) continue;
    const tableId = effectiveTable(from, primaryTable);
    const key = `${tableId}/${from.entity}.${from.attribute}`;
    const group = groups.get(key) ?? {
      target: { table_id: tableId, entity: from.entity, attribute: from.attribute },
      ids: new Set<string>(),
    };
    group.ids.add(from.id);
    group.ids.add(to.id);
    groups.set(key, group);
  }

  return [...groups.entries()].map(([key, group]) => {
    const conflictNodes = [...group.ids].map((id) => byId.get(id)).filter((node): node is EvidenceNode => !!node);
    const activeValues = new Set(
      conflictNodes
        .filter((node) => (node.status ?? "active") === "active")
        .map((node) => (node.value || node.claim).trim().toLowerCase()),
    );
    return {
      key,
      target: group.target,
      nodes: conflictNodes,
      primaryId: group.primaryId,
      resolved: group.cellConflict === false
        || (group.cellConflict !== true && activeValues.size <= 1),
    };
  }).sort((a, b) => Number(a.resolved) - Number(b.resolved) || a.key.localeCompare(b.key));
}

function relationEdges(edges: EvidenceEdge[], groups: ConflictGroup[]): EvidenceEdge[] {
  const result = [...edges];
  const signatures = new Set(edges.map((edge) => (
    `${[edge.from_id, edge.to_id].sort().join(":")}:${edge.relation}`
  )));
  for (const group of groups) {
    const [first, ...rest] = group.nodes;
    if (!first) continue;
    for (const node of rest) {
      const signature = `${[first.id, node.id].sort().join(":")}:conflict`;
      if (signatures.has(signature)) continue;
      result.push({ from_id: first.id, to_id: node.id, relation: "conflict" });
      signatures.add(signature);
    }
  }
  return result;
}

export function unresolvedConflictCount(
  nodes: EvidenceNode[],
  edges: EvidenceEdge[],
  coverageMap?: CoverageMap | null,
): number {
  return buildConflictGroups(nodes, edges, coverageMap).filter((group) => !group.resolved).length;
}

export default function EvidenceList({
  nodes,
  edges = [],
  coverageMap,
  onResolve,
  onReverify,
}: Props) {
  const [view, setView] = useState<EvidenceView>("conflicts");
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const groups = useMemo(
    () => buildConflictGroups(nodes, edges, coverageMap),
    [coverageMap, edges, nodes],
  );
  const displayEdges = useMemo(() => relationEdges(edges, groups), [edges, groups]);
  const openConflicts = groups.filter((group) => !group.resolved).length;

  if (!nodes.length) {
    return <div className="p-4 text-sm text-ink-faint">No evidence collected yet.</div>;
  }

  const resolve = async (target: RepairCellTarget, evidenceId: string) => {
    if (!onResolve || pendingId) return;
    setPendingId(evidenceId);
    setActionError(null);
    try {
      await onResolve(target, evidenceId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setPendingId(null);
    }
  };

  const tabs: { id: EvidenceView; label: string; count: number }[] = [
    { id: "conflicts", label: "Conflicts", count: openConflicts },
    { id: "relations", label: "Relations", count: displayEdges.length },
    { id: "all", label: "All", count: nodes.length },
  ];

  return (
    <div className="min-w-0">
      <div className="sticky top-[43px] z-[8] border-b border-line bg-surface px-3 py-2.5">
        <div role="tablist" aria-label="Evidence views" className="flex rounded-md bg-surface-2 p-0.5">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" role="tab" aria-selected={view === tab.id}
              onClick={() => setView(tab.id)}
              className={`min-w-0 flex-1 rounded px-2 py-1.5 text-[12px] transition-colors ${view === tab.id ? "bg-paper font-medium text-ink shadow-sm" : "text-ink-dim hover:text-ink"}`}>
              {tab.label} <span className="text-[10px] opacity-70">{tab.count}</span>
            </button>
          ))}
        </div>
        {actionError && <p role="alert" className="mt-2 text-[12px] text-err">{actionError}</p>}
      </div>

      {view === "conflicts" && (
        <div className="p-3">
          {groups.length === 0 ? (
            <div className="flex items-start gap-2 py-5 text-[13px] text-ink-dim">
              <ShieldCheck className="mt-0.5 shrink-0 text-ok" size={16} />
              <span>No evidence conflicts detected.</span>
            </div>
          ) : groups.map((group) => (
            <ConflictSection key={group.key} group={group} pendingId={pendingId}
              onResolve={onResolve ? resolve : undefined}
              onReverify={onReverify} />
          ))}
        </div>
      )}

      {view === "relations" && (
        <RelationsView edges={displayEdges} nodes={nodes} />
      )}

      {view === "all" && (
        <div className="divide-y divide-line px-3">
          {nodes.map((node) => <EvidenceRow key={node.id} node={node} />)}
        </div>
      )}
    </div>
  );
}

function ConflictSection({
  group,
  pendingId,
  onResolve,
  onReverify,
}: {
  group: ConflictGroup;
  pendingId: string | null;
  onResolve?: (target: RepairCellTarget, evidenceId: string) => Promise<void>;
  onReverify?: (target: RepairCellTarget) => void;
}) {
  return (
    <section className="border-b border-line py-3 first:pt-0 last:border-b-0">
      <div className="mb-2.5 flex items-start gap-2">
        {group.resolved
          ? <Check className="mt-0.5 shrink-0 text-ok" size={15} />
          : <AlertTriangle className="mt-0.5 shrink-0 text-err" size={15} />}
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[13px] font-semibold text-ink" title={group.key}>
            {group.target.entity} · {group.target.attribute}
          </h3>
          <p className="text-[11px] text-ink-faint">
            {group.target.table_id} · {group.resolved ? "Resolved" : `${group.nodes.length} competing sources`}
          </p>
        </div>
        {!group.resolved && onReverify && (
          <button type="button" onClick={() => onReverify(group.target)}
            className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] text-accent-ink transition-colors hover:bg-clay">
            <RefreshCw size={12} /> Verify again
          </button>
        )}
      </div>
      <div className="grid gap-2 min-[720px]:grid-cols-2 min-[1180px]:grid-cols-1 min-[1500px]:grid-cols-2">
        {group.nodes.map((node) => (
          <ConflictSource key={node.id} node={node} selected={group.primaryId === node.id}
            resolved={group.resolved} pending={pendingId === node.id} disabled={!!pendingId}
            onUse={onResolve ? () => onResolve(group.target, node.id) : undefined} />
        ))}
      </div>
    </section>
  );
}

function ConflictSource({
  node,
  selected,
  resolved,
  pending,
  disabled,
  onUse,
}: {
  node: EvidenceNode;
  selected: boolean;
  resolved: boolean;
  pending: boolean;
  disabled: boolean;
  onUse?: () => void;
}) {
  const status = node.status ?? "active";
  const excerpt = cleanExcerpt(node.source_excerpt ?? "");
  return (
    <article className={`rounded-md border p-2.5 ${status === "active" ? "border-line bg-paper/60" : "border-line bg-surface-2 opacity-65"}`}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase text-ink-dim">
              {(node.source_authority || "unclear").replace("_", " ")}
            </span>
            {selected && <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent-ink">Current</span>}
            {status !== "active" && <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] capitalize text-ink-faint">{status}</span>}
          </div>
          <p className="mt-1 text-[13px] font-medium leading-5 text-ink">{node.value || node.claim}</p>
        </div>
        {node.source && /^https?:\/\//.test(node.source) && (
          <a href={node.source} target="_blank" rel="noreferrer" title="Open source" aria-label={`Open ${sourceLabel(node.source)}`}
            className="shrink-0 rounded p-1 text-accent-ink hover:bg-clay">
            <ExternalLink size={13} />
          </a>
        )}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-[10.5px] text-ink-dim">
        <span>Quality {(quality(node) * 100).toFixed(0)}%</span>
        <span>Confidence {(node.confidence * 100).toFixed(0)}%</span>
        <span className="col-span-2 truncate" title={capturedAt(node.created_at)}>{capturedAt(node.created_at)}</span>
      </div>
      {excerpt && (
        <blockquote className="mt-2 flex gap-1.5 border-l-2 border-line-strong pl-2 text-[11.5px] italic leading-5 text-ink-dim">
          <Quote className="mt-1 shrink-0 text-ink-faint" size={10} />
          <span className="line-clamp-4">{excerpt}</span>
        </blockquote>
      )}
      <div className="mt-2.5 flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-faint" title={node.source}>{sourceLabel(node.source)}</span>
        {!resolved && status === "active" && onUse && (
          <button type="button" onClick={onUse} disabled={disabled}
            className="flex shrink-0 items-center gap-1 rounded-md bg-accent px-2 py-1 text-[11px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            {pending ? <Loader2 className="animate-spin" size={11} /> : <Check size={11} />}
            {selected ? "Keep source" : "Use source"}
          </button>
        )}
      </div>
    </article>
  );
}

function RelationsView({ edges, nodes }: { edges: EvidenceEdge[]; nodes: EvidenceNode[] }) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const counts = {
    support: edges.filter((edge) => edge.relation === "support").length,
    conflict: edges.filter((edge) => edge.relation === "conflict").length,
    refine: edges.filter((edge) => edge.relation === "refine").length,
  };
  return (
    <div className="p-3">
      <div className="mb-3 flex flex-wrap gap-1.5 text-[10.5px]">
        {(["support", "conflict", "refine"] as const).map((relation) => (
          <span key={relation} className={`rounded px-1.5 py-0.5 capitalize ${RELATION_STYLE[relation]}`}>
            {relation} {counts[relation]}
          </span>
        ))}
      </div>
      {edges.length === 0 ? (
        <div className="flex items-start gap-2 py-4 text-[13px] text-ink-dim">
          <Link2 className="mt-0.5 shrink-0" size={15} /> No evidence relations recorded.
        </div>
      ) : (
        <div className="divide-y divide-line border-y border-line">
          {edges.map((edge, index) => {
            const from = byId.get(edge.from_id);
            const to = byId.get(edge.to_id);
            return (
              <div key={`${edge.from_id}:${edge.to_id}:${edge.relation}:${index}`} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 py-2.5 text-[11.5px]">
                <span className="truncate text-ink" title={from?.claim ?? edge.from_id}>{from?.value || from?.claim || edge.from_id}</span>
                <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 capitalize ${RELATION_STYLE[edge.relation]}`}>
                  <GitCompareArrows size={10} /> {edge.relation}
                </span>
                <span className="truncate text-right text-ink" title={to?.claim ?? edge.to_id}>{to?.value || to?.claim || edge.to_id}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EvidenceRow({ node }: { node: EvidenceNode }) {
  const status = node.status ?? "active";
  return (
    <article className={`py-3 ${status === "active" ? "" : "opacity-60"}`}>
      <div className="flex items-start gap-2">
        <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${node.confidence >= 0.8 ? "bg-ok" : node.confidence >= 0.5 ? "bg-accent" : "bg-err"}`} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-5 text-ink">{node.claim}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-ink-dim">
            {node.entity && <span>{node.entity}.{node.attribute}</span>}
            <span>Quality {(quality(node) * 100).toFixed(0)}%</span>
            <span className="capitalize">{status}</span>
            {node.source && /^https?:\/\//.test(node.source) && (
              <a href={node.source} target="_blank" rel="noreferrer" className="ml-auto flex min-w-0 items-center gap-1 text-accent-ink hover:underline">
                <ExternalLink size={10} /> <span className="max-w-[150px] truncate">{sourceLabel(node.source)}</span>
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
