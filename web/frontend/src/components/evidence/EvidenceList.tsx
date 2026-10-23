"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronRight,
  ExternalLink,
  FileText,
  GitCompareArrows,
  Link2,
  Library,
  Loader2,
  Quote,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { importNetworkSource, listLocalLibraries, listNetworkImports } from "@/lib/api";
import { localCitationLabels } from "@/lib/localCitations";
import Select from "@/components/ui/Select";
import type {
  CoverageMap,
  EvidenceEdge,
  EvidenceNode,
  FrontierTask,
  TaskEvidenceBinding,
  RepairCellTarget,
} from "@/lib/types";
import type { LocalLibrary, NetworkImportJob } from "@/lib/types";

type EvidenceView = "conflicts" | "relations" | "all" | "tasks";

interface Props {
  nodes: EvidenceNode[];
  edges?: EvidenceEdge[];
  tasks?: FrontierTask[];
  taskBindings?: TaskEvidenceBinding[];
  coverageMap?: CoverageMap | null;
  onResolve?: (target: RepairCellTarget, evidenceId: string) => Promise<void>;
  onReverify?: (target: RepairCellTarget) => void;
  onOpenLocalSource?: (refId: string) => void;
  defaultView?: EvidenceView;
  sessionId?: string | null;
}

interface ConflictGroup {
  key: string;
  target: RepairCellTarget;
  nodes: EvidenceNode[];
  primaryId?: string;
  resolved: boolean;
}

interface EntityEvidenceGroup {
  entity: string;
  nodes: EvidenceNode[];
}

interface SourcePage {
  url: string;
  pageId: string;
  evidenceCount: number;
  capturedAt?: number;
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

function sourcePathLabel(source: string): string {
  try {
    const url = new URL(source);
    return `${url.pathname || "/"}${url.search}`;
  } catch {
    return source;
  }
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

export function groupEvidenceByEntity(nodes: EvidenceNode[]): EntityEvidenceGroup[] {
  const groups = new Map<string, EvidenceNode[]>();
  for (const node of nodes) {
    const entity = node.entity?.trim() || "Unassigned evidence";
    const bucket = groups.get(entity) ?? [];
    bucket.push(node);
    groups.set(entity, bucket);
  }
  return [...groups.entries()]
    .map(([entity, entityNodes]) => ({
      entity,
      nodes: entityNodes.slice().sort((a, b) => (
        Number((a.status ?? "active") !== "active")
        - Number((b.status ?? "active") !== "active")
        || a.attribute.localeCompare(b.attribute)
        || quality(b) - quality(a)
      )),
    }))
    .sort((a, b) => a.entity.localeCompare(b.entity));
}

export function evidenceSourceUrls(node: EvidenceNode): string[] {
  return [...new Set((/^(https?:|local:)\/\//.test(node.source)
    ? [node.source] : (node.source_urls ?? [])).filter((url) => /^(https?:|local:)\/\//.test(url)))];
}

export function groupEvidenceBySource(nodes: EvidenceNode[]): SourcePage[] {
  const pages = new Map<string, SourcePage>();
  for (const node of nodes) {
    for (const url of evidenceSourceUrls(node).filter((url) => /^https?:\/\//.test(url))) {
      const current = pages.get(url);
      pages.set(url, {
        url,
        // 内部执行快照不能作为原始网页的缓存正文导入。
        pageId: current?.pageId || (url === node.source ? node.page_id : "") || "",
        evidenceCount: (current?.evidenceCount ?? 0) + 1,
        capturedAt: Math.max(current?.capturedAt ?? 0, node.created_at ?? 0) || undefined,
      });
    }
  }
  return [...pages.values()].sort((a, b) => a.url.localeCompare(b.url));
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
    const schema = coverageMap?.tables[tableId];
    const attribute = schema?.attributes.find((name) => rest.endsWith(`.${name}`)
      && schema.entities.includes(rest.slice(0, -(name.length + 1))));
    const dot = attribute ? rest.length - attribute.length - 1 : rest.lastIndexOf(".");
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
    const conflictNodes = [...group.ids].map((id) => {
      const node = byId.get(id);
      const binding = coverageMap?.evidence_bindings?.[key]?.find((item) => item.evidence_id === id);
      return node && binding ? { ...node, value: binding.value, alignment: binding.alignment,
        table_id: group.target.table_id, entity: group.target.entity, attribute: group.target.attribute,
        status: node.status && node.status !== "active" ? node.status : binding.status } : node;
    }).filter((node): node is EvidenceNode => !!node);
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
  tasks = [],
  taskBindings = [],
  coverageMap,
  onResolve,
  onReverify,
  onOpenLocalSource,
  defaultView = "conflicts",
  sessionId = null,
}: Props) {
  const [view, setView] = useState<EvidenceView>(defaultView);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [libraries, setLibraries] = useState<LocalLibrary[]>([]);
  const [libraryId, setLibraryId] = useState("");
  const [indexAfterSave, setIndexAfterSave] = useState(true);
  const [imports, setImports] = useState<Record<string, NetworkImportJob>>({});
  const [selectedSources, setSelectedSources] = useState<Set<string>>(() => new Set());
  const groups = useMemo(
    () => buildConflictGroups(nodes, edges, coverageMap),
    [coverageMap, edges, nodes],
  );
  const displayEdges = useMemo(() => relationEdges(edges, groups), [edges, groups]);
  const entityGroups = useMemo(() => groupEvidenceByEntity(nodes), [nodes]);
  const sourcePages = useMemo(() => groupEvidenceBySource(nodes), [nodes]);
  const openConflicts = groups.filter((group) => !group.resolved).length;
  const hasNetworkSources = sourcePages.length > 0;

  useEffect(() => {
    if (!hasNetworkSources) return;
    void listLocalLibraries().then((items) => {
      setLibraries(items);
      setLibraryId((current) => current || items[0]?.library_id || "");
    }).catch((error) => setActionError(error instanceof Error ? error.message : String(error)));
  }, [hasNetworkSources]);

  useEffect(() => {
    const active = Object.values(imports).some((job) => ["queued", "running"].includes(job.status));
    if (!libraryId || !active) return;
    const timer = globalThis.setInterval(() => {
      void listNetworkImports(libraryId).then((jobs) => setImports((current) => {
        const next = { ...current };
        for (const job of jobs) next[job.source_url] = job;
        return next;
      })).catch(() => undefined);
    }, 1200);
    return () => globalThis.clearInterval(timer);
  }, [imports, libraryId]);

  const saveSource = async (source: SourcePage) => {
    if (!libraryId) return;
    setActionError(null);
    try {
      const job = await importNetworkSource(libraryId, source.url, {
        indexAfterSave,
        sessionId: sessionId ?? "",
        pageId: source.pageId,
      });
      setImports((current) => ({ ...current, [source.url]: job }));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };
  const toggleSource = (url: string) => setSelectedSources((current) => {
    const next = new Set(current);
    if (next.has(url)) next.delete(url); else next.add(url);
    return next;
  });
  const saveSelected = async () => {
    const byUrl = new Map(sourcePages.map((source) => [source.url, source]));
    await Promise.all([...selectedSources].map((url) => {
      const source = byUrl.get(url);
      return source ? saveSource(source) : Promise.resolve();
    }));
  };

  if (!nodes.length && !tasks.length) {
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
    ...(tasks.length ? [{ id: "tasks" as const, label: "任务", count: tasks.length }] : []),
  ];

  return (
    <div className="min-w-0">
      <div className="sticky top-[43px] z-[8] border-b border-line bg-surface px-3 py-2.5">
        {hasNetworkSources && (
          <div className="mb-2 rounded-md border border-line bg-paper p-2 text-[10.5px] text-ink-dim">
            <div className="flex flex-wrap items-center gap-2">
              <Library size={12} />
              <span className="font-medium text-ink">保存来源页面</span>
              {libraries.length ? (
                <Select ariaLabel="保存来源页面到知识库" value={libraryId} onChange={setLibraryId}
                  size="sm" className="min-w-0 flex-1"
                  options={libraries.map(library => ({ value: library.library_id, label: library.name }))} />
              ) : <span>请先创建知识库</span>}
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={indexAfterSave} onChange={(event) => setIndexAfterSave(event.target.checked)} />
                保存后索引
              </label>
              <button type="button" disabled={!libraryId || selectedSources.size === 0}
                onClick={() => void saveSelected()}
                className="rounded bg-accent px-2 py-1 font-medium text-white disabled:opacity-40">
                保存页面（{selectedSources.size}）
              </button>
            </div>
            <div className="mt-2 max-h-32 space-y-1 overflow-y-auto border-t border-line pt-1.5">
              {sourcePages.map((source) => (
                <div key={source.url} className="flex items-center gap-1.5 rounded px-1 py-1 hover:bg-surface-2">
                  <input type="checkbox" checked={selectedSources.has(source.url)}
                    onChange={() => toggleSource(source.url)} aria-label={`选择页面 ${source.url}`} />
                  <FileText size={11} className="shrink-0 text-ink-faint" />
                  <div className="min-w-0 flex-1">
                    <p className="flex min-w-0 items-center gap-1.5 text-[11px] text-ink">
                      <span className="truncate" title={source.url}>{sourceLabel(source.url)}</span>
                      <span className="shrink-0 text-[9.5px] text-ink-faint">关联 {source.evidenceCount} 条证据</span>
                    </p>
                    <p className="truncate text-[9.5px] text-ink-faint" title={source.url}>
                      {sourcePathLabel(source.url)}
                    </p>
                  </div>
                  <a href={source.url} target="_blank" rel="noreferrer" title="打开来源页面"
                    className="shrink-0 rounded p-1 text-accent-ink hover:bg-clay">
                    <ExternalLink size={11} />
                  </a>
                  <SavePageButton source={source} job={imports[source.url]}
                    disabled={!libraryId} onSave={saveSource} />
                </div>
              ))}
            </div>
          </div>
        )}
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

      {view === "tasks" && (
        <div className="space-y-2 p-3">
          {tasks.map((task) => {
            const bindings = taskBindings.filter((binding) => binding.task_id === task.id);
            const linked = bindings.flatMap((binding) => {
              const node = nodes.find((candidate) => candidate.id === binding.evidence_id);
              return node ? [{ binding, node }] : [];
            });
            return (
              <details key={task.id} className="rounded-lg border border-line" open>
                <summary className="cursor-pointer px-3 py-2 text-[12px] text-ink">
                  {task.question}
                  <span className="ml-2 text-ink-faint">{task.status} · {linked.length} 条依据</span>
                </summary>
                <div className="border-t border-line px-3">
                  {linked.length === 0 && <p className="py-3 text-[12px] text-ink-faint">尚无关联证据；执行状态不代表证据充分。</p>}
                  {linked.map(({ binding, node }) => (
                    <div key={`${node.id}:${binding.relation}`} className="border-b border-line last:border-0">
                      <span className="text-[10px] text-ink-faint">{{ supports: "支持", contradicts: "反驳", context: "背景" }[binding.relation]}</span>
                      <EvidenceRow node={node} onOpenLocalSource={onOpenLocalSource} />
                    </div>
                  ))}
                </div>
              </details>
            );
          })}
        </div>
      )}
      {view === "all" && (
        <EntityEvidenceGroups groups={entityGroups} onOpenLocalSource={onOpenLocalSource} />
      )}
    </div>
  );
}

function EntityEvidenceGroups({ groups, onOpenLocalSource }: {
  groups: EntityEvidenceGroup[];
  onOpenLocalSource?: (refId: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(groups.slice(0, 1).map((group) => group.entity)),
  );

  const toggle = (entity: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(entity)) next.delete(entity);
      else next.add(entity);
      return next;
    });
  };

  return (
    <div className="space-y-2 p-3">
      {groups.map((group) => {
        const isOpen = expanded.has(group.entity);
        const attributes = [...new Set(group.nodes.map((node) => node.attribute).filter(Boolean))];
        const sources = new Set(group.nodes.map((node) => sourceLabel(node.source))).size;
        const active = group.nodes.filter((node) => (node.status ?? "active") === "active").length;
        return (
          <section key={group.entity} className="overflow-hidden rounded-lg border border-line bg-paper/60 shadow-sm">
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => toggle(group.entity)}
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-surface-2"
            >
              <ChevronRight
                size={14}
                className={`shrink-0 text-ink-faint transition-transform ${isOpen ? "rotate-90" : ""}`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <h3 className="truncate text-[13px] font-semibold text-ink" title={group.entity}>
                    {group.entity}
                  </h3>
                  <span className="shrink-0 rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-dim">
                    {group.nodes.length}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-[10.5px] text-ink-faint">
                  {attributes.length} attributes · {sources} sources
                  {active !== group.nodes.length ? ` · ${active} active` : ""}
                </p>
              </div>
              <div className="hidden max-w-[42%] flex-wrap justify-end gap-1 min-[520px]:flex">
                {attributes.slice(0, 3).map((attribute) => (
                  <span key={attribute} className="max-w-28 truncate rounded bg-clay/50 px-1.5 py-0.5 text-[10px] text-accent-ink">
                    {attribute}
                  </span>
                ))}
                {attributes.length > 3 && (
                  <span className="px-1 py-0.5 text-[10px] text-ink-faint">+{attributes.length - 3}</span>
                )}
              </div>
            </button>
            {isOpen && (
              <div className="divide-y divide-line border-t border-line px-3">
                {group.nodes.map((node) => (
                  <EvidenceRow key={node.id} node={node} compactEntity
                    onOpenLocalSource={onOpenLocalSource} />
                ))}
              </div>
            )}
          </section>
        );
      })}
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
          <ConflictSource key={node.id} node={node} primarySelected={group.primaryId === node.id}
            resolved={group.resolved} pending={pendingId === node.id} disabled={!!pendingId}
            onUse={onResolve ? () => onResolve(group.target, node.id) : undefined} />
        ))}
      </div>
    </section>
  );
}

function ConflictSource({
  node,
  primarySelected,
  resolved,
  pending,
  disabled,
  onUse,
}: {
  node: EvidenceNode;
  primarySelected: boolean;
  resolved: boolean;
  pending: boolean;
  disabled: boolean;
  onUse?: () => void;
}) {
  const status = node.status ?? "active";
  const excerpt = cleanExcerpt(node.source_excerpt ?? "");
  return (
    <article className={`flex h-full flex-col rounded-md border p-2.5 ${status === "active" ? "border-line bg-paper/60" : "border-line bg-surface-2 opacity-65"}`}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase text-ink-dim">
              {(node.source_authority || "unclear").replace("_", " ")}
            </span>
            {primarySelected && <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent-ink">Current</span>}
            {status !== "active" && <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] capitalize text-ink-faint">{status}</span>}
          </div>
          <p className="mt-1 text-[13px] font-medium leading-5 text-ink">{node.value || node.claim}</p>
        </div>
        {evidenceSourceUrls(node).filter((url) => /^https?:\/\//.test(url)).map((url) => (
          <a key={url} href={url} target="_blank" rel="noreferrer" title="打开原始来源" aria-label={`Open ${sourceLabel(url)}`}
            className="shrink-0 rounded p-1 text-accent-ink hover:bg-clay">
            <ExternalLink size={13} />
          </a>
        ))}
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
      <div className="mt-auto flex items-center gap-2 pt-2.5">
        <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-faint" title={node.source}>{sourceLabel(node.source)}</span>
        {!resolved && status === "active" && onUse && (
          <button type="button" onClick={onUse} disabled={disabled}
            className="flex shrink-0 items-center gap-1 rounded-md bg-accent px-2 py-1 text-[11px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40">
            {pending ? <Loader2 className="animate-spin" size={11} /> : <Check size={11} />}
            {primarySelected ? "Keep source" : "Use source"}
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

function EvidenceRow({ node, compactEntity = false, onOpenLocalSource }: {
  node: EvidenceNode;
  compactEntity?: boolean;
  onOpenLocalSource?: (refId: string) => void;
}) {
  const status = node.status ?? "active";
  const sources = evidenceSourceUrls(node);
  const localLabels = localCitationLabels([], [node]);
  return (
    <article className={`py-3 ${status === "active" ? "" : "opacity-60"}`}>
      <div className="flex items-start gap-2">
        <div className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${node.confidence >= 0.8 ? "bg-ok" : node.confidence >= 0.5 ? "bg-accent" : "bg-err"}`} />
        <div className="min-w-0 flex-1">
          <p className="text-[13px] leading-5 text-ink">{node.claim}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-ink-dim">
            {node.entity && <span>{compactEntity ? node.attribute : `${node.entity}.${node.attribute}`}</span>}
            {node.alignment_note === "source_support_verified"
              ? <span>原文支持已核验</span>
              : <span>Quality {(quality(node) * 100).toFixed(0)}%</span>}
            <span className="capitalize">{status}</span>
            {sources.map((url) => url.startsWith("local://") ? (
              onOpenLocalSource && <button key={url} type="button" onClick={() => onOpenLocalSource(url)} className="ml-auto flex min-w-0 items-center gap-1 text-accent-ink hover:underline">
                <FileText size={10} /> <span className="max-w-[150px] truncate">{localLabels[url] || "本地原文"}</span>
              </button>
            ) : (
              <a key={url} href={url} target="_blank" rel="noreferrer" className="ml-auto flex min-w-0 items-center gap-1 text-accent-ink hover:underline">
                <ExternalLink size={10} /> <span className="max-w-[150px] truncate">{sourceLabel(url)}</span>
              </a>
            ))}
            {sources.length === 0 && <span>原始来源未提供</span>}
          </div>
        </div>
      </div>
    </article>
  );
}

function SavePageButton({ source, job, disabled, onSave }: {
  source: SourcePage;
  job?: NetworkImportJob;
  disabled: boolean;
  onSave: (source: SourcePage) => Promise<void>;
}) {
  const active = job?.status === "queued" || job?.status === "running";
  const label = !job ? "保存页面" : job.status === "completed"
    ? (job.stage === "saved_unindexed" ? "已保存，未索引" : "已保存并可检索")
    : job.status === "failed" ? "保存失败" : job.stage === "fetch" ? "获取中" : "处理中";
  return (
    <button type="button" disabled={disabled || active || job?.status === "completed"}
      title={job?.error || label} onClick={() => void onSave(source)}
      className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-accent-ink hover:bg-clay disabled:text-ink-faint">
      {active && <Loader2 size={10} className="animate-spin" />}{label}
    </button>
  );
}
