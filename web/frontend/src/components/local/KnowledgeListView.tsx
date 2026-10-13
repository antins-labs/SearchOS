"use client";

import { memo, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Database, FolderOpen, LibraryBig, Search } from "lucide-react";
import { FileBadge, fileAppearance } from "./knowledgeAppearance";
import type { LocalGraphNode, LocalLibraryGraph } from "@/lib/types";

interface Props {
  graph: LocalLibraryGraph;
  query: string;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
}
const PAGE_SIZE = 40;
const matches = (node: LocalGraphNode, needle: string) => !needle || `${node.label}\n${node.summary}`.toLocaleLowerCase().includes(needle);

const DocumentRow = memo(function DocumentRow({ node, selected, onSelect }: {
  node: LocalGraphNode; selected: boolean; onSelect: Props["onSelect"];
}) {
  const appearance = fileAppearance(node.document_kind, node.label);
  const ready = node.catalog_status === "ready";
  const failed = node.catalog_status === "failed";
  return <button type="button" onClick={() => onSelect(node.id)} aria-current={selected ? "true" : undefined}
    className={`knowledge-row group flex w-full items-center gap-3 rounded-xl border px-3 py-3.5 text-left ${selected ? "border-accent/40 bg-clay" : "border-line/70 bg-surface hover:border-accent/30 hover:bg-surface"}`}>
    <FileBadge kind={node.document_kind} filename={node.label} />
    <span className="min-w-0 flex-1">
      <span className="block truncate text-[13px] font-semibold text-ink" title={node.label}>{node.label}</span>
      <span className="mt-1 block truncate text-[11px] leading-5 text-ink-dim">{node.summary || "暂无摘要"}</span>
      <span data-tone={appearance.tone} className="knowledge-file-meta mt-1 inline-flex items-center gap-1.5 text-[10px]"><span className="font-semibold tracking-wide">{appearance.label}</span><span className="text-ink-faint">· {appearance.description}</span></span>
    </span>
    <span className={`flex shrink-0 items-center gap-1.5 text-[10px] ${failed ? "text-err" : "text-ink-faint"}`}>
      <i className={`h-1.5 w-1.5 rounded-full ${ready ? "bg-ok" : failed ? "bg-err" : "bg-warn"}`} />{ready ? "已编目" : failed ? "失败" : "待编目"}
    </span>
    <ChevronRight size={14} className="shrink-0 text-ink-faint opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
  </button>;
});

function DocumentGroup({ topic, documents, selectedId, onSelect, searching }: {
  topic?: LocalGraphNode; documents: LocalGraphNode[]; selectedId: string | null;
  onSelect: Props["onSelect"]; searching: boolean;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const open = searching || !collapsed;
  return <section className="knowledge-group overflow-hidden rounded-2xl border border-line bg-surface/40">
    <div className="knowledge-topic-heading flex items-center gap-2 px-3 py-3">
      <button type="button" onClick={() => setCollapsed(!collapsed)} disabled={searching} aria-expanded={open}
        aria-label={`${open ? "收起" : "展开"}${topic?.label || "待归类文档"}`} className="rounded-lg p-1.5 text-ink-faint hover:bg-surface-2 disabled:opacity-40">
        <ChevronDown size={15} className={`knowledge-chevron ${open ? "" : "-rotate-90"}`} />
      </button>
      <span className="knowledge-folder-badge"><FolderOpen size={20} strokeWidth={1.6} /></span>
      {topic ? <button type="button" onClick={() => onSelect(topic.id)} aria-current={selectedId === topic.id ? "true" : undefined}
        className={`min-w-0 flex-1 truncate rounded-md px-1 text-left text-[13px] font-semibold hover:text-accent-ink ${selectedId === topic.id ? "text-accent-ink" : "text-ink"}`}><span className="mb-0.5 block text-[9px] font-medium tracking-widest text-ink-faint">主题目录</span><span className="block truncate">{topic.label}</span></button>
        : <h3 className="min-w-0 flex-1 text-[13px] font-semibold text-ink">待归类文档</h3>}
      <span className="rounded-full border border-line/70 bg-surface px-2 py-1 text-[10px] tabular-nums text-ink-dim">{documents.length} 份</span>
    </div>
    {open && <div className="space-y-2 border-t border-line/70 p-2.5">
      {documents.slice(0, limit).map((node) => <DocumentRow key={node.id} node={node} selected={selectedId === node.id} onSelect={onSelect} />)}
      {documents.length === 0 && <p className="px-4 py-5 text-xs text-ink-faint">该主题暂无文档</p>}
      {documents.length > limit && <button type="button" onClick={() => setLimit(limit + PAGE_SIZE)} className="w-full rounded-lg py-3 text-xs text-accent-ink hover:bg-clay">再显示 {Math.min(PAGE_SIZE, documents.length - limit)} 份 · 还有 {documents.length - limit} 份</button>}
    </div>}
  </section>;
}

export default memo(function KnowledgeListView({ graph, query, selectedId, onSelect }: Props) {
  const needle = query.trim().toLocaleLowerCase();
  const { root, groups, unclassified, count } = useMemo(() => {
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const linked = new Set<string>();
    const byTopic = new Map<string, Set<string>>();
    for (const edge of graph.edges) {
      if (byId.get(edge.source)?.node_type !== "subindex" || byId.get(edge.target)?.node_type !== "document") continue;
      const ids = byTopic.get(edge.source) ?? new Set<string>();
      ids.add(edge.target);
      byTopic.set(edge.source, ids);
      linked.add(edge.target);
    }
    const groups = graph.nodes.filter((n) => n.node_type === "subindex").sort((a, b) => a.label.localeCompare(b.label)).flatMap((topic) => {
      const documents = Array.from(byTopic.get(topic.id) ?? [], (id) => byId.get(id)!).filter((node) => matches(topic, needle) || matches(node, needle));
      return needle && !matches(topic, needle) && !documents.length ? [] : [{ topic, documents }];
    });
    const unclassified = graph.nodes.filter((node) => node.node_type === "document" && !linked.has(node.id) && matches(node, needle));
    const visibleIds = new Set([...groups.flatMap((group) => group.documents.map((node) => node.id)), ...unclassified.map((node) => node.id)]);
    return { root: graph.nodes.find((node) => node.node_type === "index"), groups, unclassified, count: visibleIds.size };
  }, [graph, needle]);

  return <div className="h-full overflow-y-auto bg-paper p-4 sm:p-6" aria-label="知识库索引列表">
    <div className="mb-5 flex items-start justify-between gap-3">
      <div><h2 className="text-[18px] font-semibold tracking-tight text-ink">{needle ? "搜索结果" : "文档与主题"}</h2>
        <p className="mt-1 text-xs text-ink-faint" role="status">{needle ? `找到 ${count} 份文档 · ${groups.length} 个主题` : "按主题整理，随时查阅与引用"}</p></div>
      {root && <button type="button" onClick={() => onSelect(root.id)} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 py-2 text-[11px] text-ink-dim hover:bg-surface-2"><Database size={13} />总览</button>}
    </div>
    {root && !needle && <button type="button" onClick={() => onSelect(root.id)} aria-current={selectedId === root.id ? "true" : undefined}
      className="knowledge-root-card group relative mb-5 flex w-full items-center gap-4 overflow-hidden rounded-2xl p-5 text-left">
      <span className="relative grid h-14 w-14 shrink-0 place-items-center rounded-2xl border border-line bg-surface/70 text-ink-dim"><LibraryBig size={28} strokeWidth={1.5} /></span>
      <span className="relative min-w-0 flex-1"><span className="mb-1 block text-[10px] tracking-[0.16em] text-ink-faint">知识库 · 总目录</span>
        <span className="block truncate text-[18px] font-semibold tracking-tight">{root.label}</span>
        <span className="mt-2 flex gap-3 text-[11px] text-ink-dim"><span>{groups.length} 个主题</span><span className="text-ink-faint/40">/</span><span>{count} 份文档</span></span>
      </span><ChevronRight size={18} className="relative shrink-0 text-ink-faint" />
    </button>}
    {!groups.length && !unclassified.length ? <div className="grid min-h-64 place-items-center text-center">
      <div><Search size={26} strokeWidth={1.5} className="mx-auto mb-3 text-ink-faint" /><p className="text-sm text-ink-dim">{needle ? "没有找到匹配的内容" : "从第一份文档开始"}</p><p className="mt-2 text-xs text-ink-faint">{needle ? "试试更短的关键词，或搜索文档摘要" : "点击上方「添加文档」，自动生成主题索引"}</p></div>
    </div> : <div className="space-y-3">
      {groups.map(({ topic, documents }) => <DocumentGroup key={`${topic.id}:${needle}`} topic={topic} documents={documents} selectedId={selectedId} onSelect={onSelect} searching={!!needle} />)}
      {!!unclassified.length && <DocumentGroup key={`unclassified:${needle}`} documents={unclassified} selectedId={selectedId} onSelect={onSelect} searching={!!needle} />}
    </div>}
  </div>;
});
