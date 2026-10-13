"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { FolderOpen, LibraryBig, Layers, LocateFixed, Minus, Plus } from "lucide-react";

import { fileAppearance } from "./knowledgeAppearance";
import useKnowledgeGraphMotion, { graphCurve } from "@/hooks/useKnowledgeGraphMotion";
import { layoutKnowledgeGraph } from "@/lib/knowledgeGraph";
import type { LocalGraphNode, LocalLibraryGraph } from "@/lib/types";

interface Props {
  graph: LocalLibraryGraph;
  query: string;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
  onMoveDocument: (documentId: string, subindexId: string | null) => void;
  onDeleteRelation: (documentId: string, subindexId: string) => void;
  mutatingDocumentId?: string | null;
}

function trimLabel(value: string, limit: number): string {
  let width = 0;
  let label = "";
  for (const character of value) {
    width += /[\u0000-\u00ff]/.test(character) ? 0.55 : 1;
    if (width > limit - 1) return `${label}…`;
    label += character;
  }
  return label;
}

function filteredGraph(graph: LocalLibraryGraph, query: string): LocalLibraryGraph {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return graph;
  const direct = new Set(graph.nodes.filter((node) => (
    `${node.label}\n${node.summary}`.toLocaleLowerCase().includes(needle)
  )).map((node) => node.id));
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const visible = new Set(direct);
  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of graph.edges) {
      if (visible.has(edge.target) && !visible.has(edge.source)) {
        visible.add(edge.source);
        changed = true;
      }
      const source = byId.get(edge.source);
      if (direct.has(edge.source) && source?.node_type === "subindex" && !visible.has(edge.target)) {
        visible.add(edge.target);
        changed = true;
      }
    }
  }
  return {
    ...graph,
    nodes: graph.nodes.filter((node) => visible.has(node.id)),
    edges: graph.edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target)),
  };
}

export default function KnowledgeGraphView({
  graph,
  query,
  selectedId,
  onSelect,
  onMoveDocument,
  onDeleteRelation,
  mutatingDocumentId,
}: Props) {
  const visibleGraph = useMemo(() => filteredGraph(graph, query), [graph, query]);
  const [openedGroupIds, setOpenedGroupIds] = useState<Set<string>>(new Set());
  const [expandedGroupIds, setExpandedGroupIds] = useState<Set<string>>(new Set());
  const layout = useMemo(() => layoutKnowledgeGraph(visibleGraph, {
    expandedGroupIds,
    openedGroupIds: query.trim() ? new Set(visibleGraph.nodes.filter((node) => node.node_type === "subindex").map((node) => node.id).concat("__root_documents__")) : openedGroupIds,
    stackThreshold: query.trim() ? Number.MAX_SAFE_INTEGER : 3,
  }), [expandedGroupIds, openedGroupIds, query, visibleGraph]);
  const svgRef = useRef<SVGSVGElement>(null);
  useKnowledgeGraphMotion(svgRef, layout);
  const viewportRef = useRef<SVGGElement>(null);
  const [viewport, setViewport] = useState({ width: 1000, height: 700 });
  const initializedView = useRef(false);
  const [cameraAnimated, setCameraAnimated] = useState(false);
  const panFrame = useRef<number | null>(null);
  const pendingOffset = useRef({ x: 0, y: 0 });
  useEffect(() => () => { if (panFrame.current !== null) cancelAnimationFrame(panFrame.current); }, []);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const documentDragRef = useRef<{
    node: LocalGraphNode & { x: number; y: number; width: number; height: number };
    documentId: string;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const [documentDrag, setDocumentDrag] = useState<{ nodeId: string; x: number; y: number } | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (!width || !height) return;
      setViewport((value) => value.width === width && value.height === height ? value : { width, height });
      if (!initializedView.current) {
        const fit = Math.min(1, (width - 48) / layout.width, (height - 64) / layout.height);
        setScale(Math.max(0.8, fit));
        setOffset({ x: (width - layout.width * Math.max(0.8, fit)) / 2, y: 24 });
        initializedView.current = true;
      }
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, [layout.width, layout.height]);

  const focusGroup = (groupId: string, opened: Set<string>, expanded: Set<string>) => {
    const next = layoutKnowledgeGraph(visibleGraph, { openedGroupIds: opened, expandedGroupIds: expanded });
    const members = next.nodes.filter((node) => !node.hidden && (!opened.has(groupId) || node.id === groupId || node.groupId === groupId));
    if (!members.length) return;
    const left = Math.min(...members.map((node) => node.x - node.width / 2)) - 36;
    const right = Math.max(...members.map((node) => node.x + node.width / 2)) + 36;
    const top = Math.min(...members.map((node) => node.y - node.height / 2)) - 48;
    const bottom = Math.max(...members.map((node) => node.y + node.height / 2)) + 48;
    const nextScale = Math.max(0.15, Math.min(1.1, viewport.width / (right - left), viewport.height / (bottom - top)));
    setCameraAnimated(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    setScale(nextScale);
    setOffset({ x: viewport.width / 2 - (left + right) / 2 * nextScale, y: viewport.height / 2 - (top + bottom) / 2 * nextScale });
  };
  const toggleTopic = (id: string) => {
    const opened = new Set(openedGroupIds);
    if (opened.has(id)) opened.delete(id); else opened.add(id);
    const expanded = new Set(expandedGroupIds);
    expanded.delete(id);
    setOpenedGroupIds(opened);
    setExpandedGroupIds(expanded);
    focusGroup(id, opened, expanded);
    onSelect(id);
  };
  const focusNode = (id: string) => {
    const node = Array.from(svgRef.current?.querySelectorAll<SVGGElement>("[data-graph-node]") ?? []).find((element) => element.dataset.graphNode === id);
    node?.focus();
  };
  const expandStack = (id: string) => {
    focusNode(id);
    const expanded = new Set(expandedGroupIds).add(id);
    setExpandedGroupIds(expanded);
    focusGroup(id, openedGroupIds, expanded);
  };
  const collapseOverview = () => {
    const next = layoutKnowledgeGraph(visibleGraph);
    const fit = Math.min(1, (viewport.width - 48) / next.width, (viewport.height - 64) / next.height);
    setOpenedGroupIds(new Set());
    setExpandedGroupIds(new Set());
    setCameraAnimated(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    setScale(fit);
    setOffset({ x: (viewport.width - next.width * fit) / 2, y: 24 });
    const root = visibleGraph.nodes.find((node) => node.node_type === "index");
    if (root) { onSelect(root.id); focusNode(root.id); }
  };
  const changeScale = (next: number) => {
    setCameraAnimated(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const value = Math.min(3.5, Math.max(0.15, next));
    setOffset((current) => ({
      x: viewport.width / 2 - (viewport.width / 2 - current.x) * value / scale,
      y: viewport.height / 2 - (viewport.height / 2 - current.y) * value / scale,
    }));
    setScale(value);
  };
  const svgPoint = (svg: SVGSVGElement, x: number, y: number) => {
    const matrix = svg.getScreenCTM();
    return matrix ? new DOMPoint(x, y).matrixTransform(matrix.inverse()) : { x, y };
  };
  const resetView = () => {
    setCameraAnimated(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const fit = Math.min(1.2, (viewport.width - 64) / layout.width, (viewport.height - 80) / layout.height);
    setScale(fit);
    setOffset({ x: (viewport.width - layout.width * fit) / 2, y: (viewport.height - layout.height * fit) / 2 });
  };
  const beginPan = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0 || event.target !== event.currentTarget) return;
    setCameraAnimated(false);
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = svgPoint(event.currentTarget, event.clientX, event.clientY);
    pendingOffset.current = offset;
    dragRef.current = { x: point.x, y: point.y, offsetX: offset.x, offsetY: offset.y };
  };
  const movePan = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const point = svgPoint(event.currentTarget, event.clientX, event.clientY);
    pendingOffset.current = { x: drag.offsetX + point.x - drag.x, y: drag.offsetY + point.y - drag.y };
    if (panFrame.current === null) panFrame.current = requestAnimationFrame(() => {
      const next = pendingOffset.current;
      if (viewportRef.current) viewportRef.current.style.transform = `translate(${next.x}px, ${next.y}px) scale(${scale})`;
      panFrame.current = null;
    });
  };
  const endPan = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragRef.current) return;
    if (panFrame.current !== null) cancelAnimationFrame(panFrame.current);
    panFrame.current = null;
    setOffset(pendingOffset.current);
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const wheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      setCameraAnimated(false);
      const point = svgPoint(svg, event.clientX, event.clientY);
      const next = Math.min(3.5, Math.max(0.15, scale * Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * 0.003)));
      setOffset((current) => ({
        x: point.x - (point.x - current.x) * next / scale,
        y: point.y - (point.y - current.y) * next / scale,
      }));
      setScale(next);
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => svg.removeEventListener("wheel", wheel);
  }, [scale]);
  const graphPoint = (event: ReactPointerEvent<SVGElement>) => {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return { x: 0, y: 0 };
    const point = svgPoint(svg, event.clientX, event.clientY);
    return { x: (point.x - offset.x) / scale, y: (point.y - offset.y) / scale };
  };
  const dropTargetAt = (point: { x: number; y: number }) => layout.nodes.find((node) => (
    (node.node_type === "subindex" || node.node_type === "index")
    && point.x >= node.x - node.width / 2
    && point.x <= node.x + node.width / 2
    && point.y >= node.y - node.height / 2
    && point.y <= node.y + node.height / 2
  ));
  const beginDocumentDrag = (
    event: ReactPointerEvent<SVGGElement>,
    node: LocalGraphNode & { x: number; y: number; width: number; height: number },
  ) => {
    if (event.button !== 0 || !node.document_id || mutatingDocumentId) return;
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    documentDragRef.current = {
      node,
      documentId: node.document_id,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    setDocumentDrag({ nodeId: node.id, x: node.x, y: node.y });
  };
  const moveDocumentDrag = (event: ReactPointerEvent<SVGGElement>) => {
    const drag = documentDragRef.current;
    if (!drag) return;
    event.stopPropagation();
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const start = svgPoint(svg, drag.startX, drag.startY);
    const point = svgPoint(svg, event.clientX, event.clientY);
    const x = drag.node.x + (point.x - start.x) / scale;
    const y = drag.node.y + (point.y - start.y) / scale;
    if (Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY) > 5) {
      drag.moved = true;
    }
    setDocumentDrag({ nodeId: drag.node.id, x, y });
    setDropTargetId(dropTargetAt(graphPoint(event))?.id ?? null);
  };
  const endDocumentDrag = (event: ReactPointerEvent<SVGGElement>) => {
    const drag = documentDragRef.current;
    if (!drag) return;
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const target = drag.moved ? dropTargetAt(graphPoint(event)) : null;
    documentDragRef.current = null;
    setDocumentDrag(null);
    setDropTargetId(null);
    onSelect(drag.node.id);
    if (target?.node_type === "subindex" && target.subindex_id) {
      onMoveDocument(drag.documentId, target.subindex_id);
    } else if (target?.node_type === "index") {
      onMoveDocument(drag.documentId, null);
    }
  };
  const cancelDocumentDrag = (event: ReactPointerEvent<SVGGElement>) => {
    if (!documentDragRef.current) return;
    event.stopPropagation();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    documentDragRef.current = null;
    setDocumentDrag(null);
    setDropTargetId(null);
  };

  if (layout.nodes.length === 0) {
    return <div className="grid h-full min-h-80 place-items-center text-[13px] text-ink-faint">没有匹配的索引节点</div>;
  }

  return (
    <div className="relative h-full min-h-[28rem] overflow-hidden bg-paper">
      <div className="absolute right-4 top-4 z-10 flex items-center rounded-lg border border-line bg-surface p-1 shadow-sm">
        {(openedGroupIds.size > 0 || expandedGroupIds.size > 0) && <button type="button" onClick={collapseOverview} className="mr-1 flex items-center gap-1 rounded-md px-2 py-1.5 text-[11px] text-ink-dim hover:bg-surface-2" aria-label="收起全部文档堆"><Layers size={13} />收起</button>}
        <button type="button" onClick={() => changeScale(scale / 1.2)} className="rounded-md p-1.5 text-ink-dim hover:bg-surface-2" aria-label="缩小图"><Minus size={14} /></button>
        <span className="w-11 text-center text-[11px] tabular-nums text-ink-faint">{Math.round(scale * 100)}%</span>
        <button type="button" onClick={() => changeScale(scale * 1.2)} className="rounded-md p-1.5 text-ink-dim hover:bg-surface-2" aria-label="放大图"><Plus size={14} /></button>
        <button type="button" onClick={resetView} className="ml-1 rounded-md border-l border-line p-1.5 text-ink-dim hover:bg-surface-2" aria-label="复位图"><LocateFixed size={14} /></button>
      </div>
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
        role="group"
        aria-label={`知识库索引图，共 ${layout.nodes.filter((node) => !node.hidden).length} 个节点、${layout.edges.length} 条关系`}
        style={{ touchAction: "none" }}
        onPointerDown={beginPan}
        onPointerMove={movePan}
        onPointerUp={endPan}
        onPointerCancel={endPan}
      >
        <defs>
          <pattern id="knowledge-grid" width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" className="fill-line" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#knowledge-grid)" className="pointer-events-none" />
        <g ref={viewportRef} style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`, transition: cameraAnimated ? "transform 280ms cubic-bezier(0.2, 0.8, 0.2, 1)" : "none" }}>
          <g className="pointer-events-none">
            {layout.edges.map((edge, index) => {
              const active = !selectedId || edge.source === selectedId || edge.target === selectedId;
              const x1 = edge.sourceNode.x;
              const y1 = edge.sourceNode.y;
              const x2 = edge.targetNode.x;
              const y2 = edge.targetNode.y;
              return (
                <path
                  key={`${edge.source}-${edge.target}-${index}`}
                  data-graph-edge="true"
                  data-graph-source={edge.source}
                  data-graph-target={edge.target}
                  d={graphCurve({ x: x1, y: y1 }, { x: x2, y: y2 })}
                  fill="none"
                  className={edge.relation === "pending_catalog"
                    ? `stroke-warn ${active ? "opacity-70" : "opacity-35"}`
                    : `stroke-line-strong ${active ? "opacity-80" : "opacity-35"}`}
                  strokeWidth={active ? 2 : 1.25}
                  strokeDasharray={edge.relation === "pending_catalog" ? "7 6" : undefined}
                />
              );
            })}
          </g>
          <g>
            {layout.edges.map((edge, index) => {
              if (edge.targetNode.stack || mutatingDocumentId || edge.relation !== "classifies" || (selectedId !== edge.target)) return null;
              const documentId = edge.targetNode.document_id;
              const subindexId = edge.sourceNode.subindex_id;
              if (!documentId || !subindexId) return null;
              const x = (edge.sourceNode.x + edge.targetNode.x) / 2;
              const y = (edge.sourceNode.y + edge.targetNode.y) / 2;
              return (
                <g
                  key={`delete-${edge.source}-${edge.target}-${index}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`删除 ${edge.sourceNode.label} 与 ${edge.targetNode.label} 的关系`}
                  transform={`translate(${x} ${y})`}
                  className="cursor-pointer outline-none"
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteRelation(documentId, subindexId);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onDeleteRelation(documentId, subindexId);
                    }
                  }}
                >
                  <title>删除这条分类关系</title>
                  <circle r={11} className="fill-surface stroke-err" strokeWidth={1.5} />
                  <path d="M -3 -3 L 3 3 M 3 -3 L -3 3" className="stroke-err" strokeWidth={1.5} strokeLinecap="round" />
                </g>
              );
            })}
          </g>
          {layout.nodes.map((node) => {
            const selected = node.id === selectedId;
            const appearance = fileAppearance(node.document_kind, node.label);
            const NodeIcon = node.node_type === "index" ? LibraryBig : node.node_type === "subindex" ? FolderOpen : node.stack ? Layers : appearance.Icon;

            const statusClass = node.node_type !== "document" || node.stack
              ? "fill-accent"
              : node.catalog_status === "ready"
                ? "fill-ok"
                : node.catalog_status === "failed"
                  ? "fill-err"
                  : "fill-warn";
            const dragged = documentDrag?.nodeId === node.id;
            const nodeX = dragged ? documentDrag.x : node.x;
            const nodeY = dragged ? documentDrag.y : node.y;
            const dropTarget = dropTargetId === node.id;
            return (
              <g
                key={node.id}
                data-graph-node={node.id}
                aria-hidden={node.hidden || undefined}
                data-level={node.node_type === "index" ? "root" : node.node_type === "subindex" ? "topic" : "file"}
                data-tone={node.node_type === "document" ? appearance.tone : undefined}
                aria-pressed={selected}
                aria-expanded={node.stack ? false : node.node_type === "subindex" ? openedGroupIds.has(node.id) : undefined}
                role="button"
                tabIndex={node.hidden ? -1 : 0}
                aria-label={node.stack ? `文档堆：${node.stack.count} 份文档，点击展开` : `${node.node_type === "index" ? "总索引" : node.node_type === "subindex" ? "主题" : "文档"}：${node.label}`}
                transform={`translate(${nodeX - node.width / 2} ${nodeY - node.height / 2})`}
                className={`knowledge-node ${node.node_type === "document" && !node.stack ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"} outline-none`}
                style={{ pointerEvents: node.hidden ? "none" : undefined }}
                onPointerDown={(event) => {
                  if (node.node_type === "document" && !node.stack) beginDocumentDrag(event, node);
                }}
                onPointerMove={(event) => {
                  if (node.node_type === "document" && !node.stack) moveDocumentDrag(event);
                }}
                onPointerUp={(event) => {
                  if (node.node_type === "document" && !node.stack) endDocumentDrag(event);
                }}
                onPointerCancel={(event) => {
                  if (node.node_type === "document" && !node.stack) cancelDocumentDrag(event);
                }}
                onClick={() => {
                  if (node.stack) {
                    expandStack(node.stack!.groupId);
                    return;
                  }
                  if (node.node_type === "subindex") toggleTopic(node.id);
                  else onSelect(node.id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    if (node.stack) expandStack(node.stack!.groupId);
                    else if (node.node_type === "subindex") toggleTopic(node.id);
                    else onSelect(node.id);
                  }
                }}
              >
                <title>{node.stack ? `${node.stack.count} 份文档，点击展开` : `${node.node_type === "index" ? "总索引" : node.node_type === "subindex" ? "主题" : "文档"}：${node.label}`}</title>
                {node.stack && <>
                  <rect x={10} y={10} width={node.width} height={node.height} rx={12} className="fill-surface stroke-line opacity-45" />
                  <rect x={5} y={5} width={node.width} height={node.height} rx={12} className="fill-surface stroke-line opacity-70" />
                </>}
                <rect
                  width={node.width}
                  height={node.height}
                  rx={node.node_type === "index" ? 16 : 10}
                  className={`knowledge-node-body ${dropTarget ? "fill-clay stroke-ok" : selected ? "fill-clay stroke-accent" : "fill-surface stroke-line"} transition-colors`}
                  strokeWidth={dropTarget || selected ? 2.5 : 1.25}
                />
                <g className="pointer-events-none">
                  <rect x={14} y={17} width={38} height={42} rx={9} className="knowledge-node-icon-bg" />
                  <NodeIcon x={22} y={26} width={22} height={22} strokeWidth={1.6} className="knowledge-node-icon" />
                  <text x={64} y={28} className="knowledge-node-caption fill-ink-faint text-[11px]" letterSpacing="0.5">
                    {node.node_type === "index" ? "知识库 / 总目录" : node.node_type === "subindex" ? "主题目录" : node.stack ? "文档集合" : `${appearance.label} · ${appearance.description}`}
                  </text>
                  <text x={64} y={49} className="knowledge-node-title fill-ink text-[14px] font-semibold">
                    {node.stack ? `${node.stack.count} 份文档` : trimLabel(node.label, node.node_type === "document" ? 15 : 13)}
                  </text>
                  <path d={`M 14 68 H ${node.width - 14}`} className="stroke-line" />
                  <text x={16} y={85} className="knowledge-node-caption fill-ink-faint text-[11px]">
                    {node.node_type === "index" ? trimLabel(node.summary, 22)
                      : node.node_type === "subindex" ? `${node.document_count ?? 0} 份文档 · ${openedGroupIds.has(node.id) ? "点击收起" : "点击展开"}`
                      : node.stack ? "点击展开文档堆"
                      : node.catalog_status === "ready" ? "已编目" : node.catalog_status === "failed" ? "编目失败" : "等待编目"}
                  </text>
                  {node.node_type === "document" && !node.stack && <circle cx={node.width - 18} cy={81} r={3} className={statusClass} />}
                </g>
              </g>
            );
          })}
        </g>
      </svg>
      <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-3 rounded-lg bg-paper/90 px-2.5 py-1.5 text-[11px] text-ink-faint backdrop-blur-sm">
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-accent" />索引/主题</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-ok" />已编目</span>
        <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-warn" />处理中</span>
      </div>
      {documentDrag && <div className="pointer-events-none absolute bottom-3 right-3 rounded-lg border border-accent bg-paper/95 px-3 py-2 text-[11px] text-ink-dim shadow-sm">拖到主题以添加关联；拖到总索引以移除全部关系</div>}
    </div>
  );
}
