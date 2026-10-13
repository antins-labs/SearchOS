import type { LocalGraphEdge, LocalGraphNode, LocalLibraryGraph } from "@/lib/types";

export interface PositionedGraphNode extends LocalGraphNode {
  x: number;
  y: number;
  width: number;
  height: number;
  hidden?: boolean;
  groupId?: string;
  stack?: { groupId: string; count: number; memberIds: string[] };
}

export interface PositionedGraphEdge extends LocalGraphEdge {
  sourceNode: PositionedGraphNode;
  targetNode: PositionedGraphNode;
}

export interface KnowledgeGraphLayout {
  width: number;
  height: number;
  nodes: PositionedGraphNode[];
  edges: PositionedGraphEdge[];
}

export interface KnowledgeGraphLayoutOptions {
  expandedGroupIds?: ReadonlySet<string>;
  openedGroupIds?: ReadonlySet<string>;
  stackThreshold?: number;
}

const NODE_SIZE = {
  index: { width: 260, height: 104 },
  subindex: { width: 260, height: 100 },
  document: { width: 280, height: 96 },
} as const;

const ROOT_GROUP = "__root_documents__";

/** Compact radial neighborhoods; reveal state never changes the underlying graph edges. */
export function layoutKnowledgeGraph(
  graph: LocalLibraryGraph,
  options: KnowledgeGraphLayoutOptions = {},
): KnowledgeGraphLayout {
  const stackThreshold = options.stackThreshold ?? 3;
  const expanded = options.expandedGroupIds ?? new Set<string>();
  const roots = graph.nodes.filter((node) => node.node_type === "index");
  const topics = graph.nodes
    .filter((node) => node.node_type === "subindex")
    .sort((a, b) => a.label.localeCompare(b.label));
  const documents = graph.nodes.filter((node) => node.node_type === "document");
  const topicOrder = new Map(topics.map((node, index) => [node.id, index]));
  const documentGroups = new Map<string, LocalGraphNode[]>();

  const opened = options.openedGroupIds ?? new Set<string>();
  const memberships = new Map<string, string[]>();
  const primaryTopic = new Map<string, string>();
  for (const edge of graph.edges) {
    if (!topicOrder.has(edge.source)) continue;
    memberships.set(edge.target, [...(memberships.get(edge.target) ?? []), edge.source]);
    const previous = primaryTopic.get(edge.target);
    if (!previous || (opened.has(edge.source) && !opened.has(previous)) || (opened.has(edge.source) === opened.has(previous) && topicOrder.get(edge.source)! < topicOrder.get(previous)!)) primaryTopic.set(edge.target, edge.source);
  }
  for (const document of documents) {
    const groupId = primaryTopic.get(document.id) ?? ROOT_GROUP;
    const group = documentGroups.get(groupId) ?? [];
    group.push(document);
    documentGroups.set(groupId, group);
  }
  for (const group of documentGroups.values()) group.sort((a, b) => a.label.localeCompare(b.label));

  const groupIds = [...topics.map((topic) => topic.id), ...(documentGroups.has(ROOT_GROUP) ? [ROOT_GROUP] : [])];
  const positioned: PositionedGraphNode[] = [];
  // Spatial buckets keep collision checks local, including for large expanded libraries.
  const buckets = new Map<string, PositionedGraphNode[]>();
  const cells = (x: number, y: number, width: number, height: number) => {
    const keys: string[] = [];
    for (let ix = Math.floor((x - width / 2 - 20) / 320); ix <= Math.floor((x + width / 2 + 20) / 320); ix++) {
      for (let iy = Math.floor((y - height / 2 - 20) / 140); iy <= Math.floor((y + height / 2 + 20) / 140); iy++) keys.push(`${ix}:${iy}`);
    }
    return keys;
  };
  const place = (node: PositionedGraphNode) => {
    const origin = { x: node.x, y: node.y };
    const free = (x: number, y: number) => cells(x, y, node.width, node.height).every((key) =>
      (buckets.get(key) ?? []).every((other) => Math.abs(x - other.x) >= (node.width + other.width) / 2 + 24
        || Math.abs(y - other.y) >= (node.height + other.height) / 2 + 24));
    // Search both axes around the preferred graph position, never push a whole column down.
    for (let ring = 0; ; ring++) {
      const count = ring ? Math.max(12, ring * 8) : 1;
      let found = false;
      for (let step = 0; step < count; step++) {
        const angle = step * Math.PI * 2 / count;
        const x = origin.x + Math.cos(angle) * ring * 48;
        const y = origin.y + Math.sin(angle) * ring * 28;
        if (!free(x, y)) continue;
        node.x = x;
        node.y = y;
        found = true;
        break;
      }
      if (found) break;
    }
    positioned.push(node);
    for (const key of cells(node.x, node.y, node.width, node.height)) {
      buckets.set(key, [...(buckets.get(key) ?? []), node]);
    }
  };
  roots.forEach((node) => place({ ...node, x: 0, y: 0, ...NODE_SIZE.index }));
  const topicPositions = new Map<string, PositionedGraphNode>();
  groupIds.forEach((groupId, index) => {
    const topic = topics.find((node) => node.id === groupId) ?? {
      id: ROOT_GROUP, node_type: "subindex" as const, label: "未归类文件", summary: "尚未关联主题的文件",
      document_count: documentGroups.get(groupId)?.length ?? 0,
    };
    const angle = -Math.PI / 2 + index * Math.PI * 2 / groupIds.length;
    const radius = Math.max(1, Math.sqrt(groupIds.length / 6));
    const node = { ...topic, x: Math.cos(angle) * 340 * radius, y: Math.sin(angle) * 200 * radius, ...NODE_SIZE.subindex };
    place(node);
    topicPositions.set(groupId, node);
  });
  const representativeByDocument = new Map<string, string>();
  for (const groupId of groupIds) {
    const topic = topicPositions.get(groupId)!;
    const group = documentGroups.get(groupId) ?? [];
    const isOpen = opened.has(groupId);
    const canStack = group.length >= stackThreshold;
    const collapsed = canStack && !expanded.has(groupId);
    const stackId = `stack:${groupId}`;
    const outward = Math.atan2(topic.y / 200, topic.x / 340);
    const stack = canStack ? { ...group[0], id: stackId, x: topic.x + Math.cos(outward) * 310,
      y: topic.y + Math.sin(outward) * 160, ...NODE_SIZE.document, groupId, hidden: !isOpen || !collapsed,
      stack: { groupId, count: group.length, memberIds: group.map((node) => node.id) } } : undefined;
    if (stack) {
      if (!stack.hidden) place(stack); else positioned.push(stack);
    }
    group.forEach((node, index) => {
      const links = (memberships.get(node.id) ?? []).map((id) => topicPositions.get(id)!).filter(Boolean);
      const shared = links.length > 1;
      const angle = outward + index * Math.PI * 2 / Math.max(group.length, 1);
      // Shared files occupy the space between their topics and retain every membership edge.
      const x = shared ? links.reduce((sum, item) => sum + item.x, 0) / links.length : topic.x + Math.cos(outward) * 260 + Math.cos(angle) * 220;
      const y = shared ? links.reduce((sum, item) => sum + item.y, 0) / links.length : topic.y + Math.sin(outward) * 160 + Math.sin(angle) * 150;
      const document = { ...node, x, y, ...NODE_SIZE.document, groupId, hidden: !isOpen || collapsed };
      if (document.hidden) positioned.push(document); else place(document);
      representativeByDocument.set(node.id, collapsed ? stackId : node.id);
    });
  }
  // Hidden nodes remain mounted at their visible parent/stack so motion can run in either direction.
  for (const node of positioned.filter((node) => node.hidden)) {
    const topic = topicPositions.get(node.groupId!)!;
    const stack = positioned.find((item) => item.id === `stack:${node.groupId}` && !item.hidden);
    const origin = stack ?? topic;
    node.x = origin.x;
    node.y = origin.y;
  }
  const visible = positioned.filter((node) => !node.hidden);
  const left = Math.min(0, ...visible.map((node) => node.x - node.width / 2)) - 32;
  const top = Math.min(0, ...visible.map((node) => node.y - node.height / 2)) - 32;
  const width = Math.max(320, ...visible.map((node) => node.x + node.width / 2 + 32 - left));
  const height = Math.max(320, ...visible.map((node) => node.y + node.height / 2 + 32 - top));
  positioned.forEach((node) => { node.x -= left; node.y -= top; });

  const byId = new Map(positioned.map((node) => [node.id, node]));
  const edgeKeys = new Set<string>();
  const edges = graph.edges.flatMap((edge) => {
    const targetId = representativeByDocument.get(edge.target) ?? edge.target;
    const sourceId = edge.relation === "pending_catalog" ? ROOT_GROUP : edge.source;
    const sourceNode = byId.get(sourceId);
    const targetNode = byId.get(targetId);
    const key = `${edge.source}:${targetId}:${edge.relation}`;
    if (!sourceNode || !targetNode || sourceNode.hidden || targetNode.hidden || edgeKeys.has(key)) return [];
    edgeKeys.add(key);
    return [{ ...edge, source: sourceId, target: targetId, sourceNode, targetNode }];
  });
  if (documentGroups.has(ROOT_GROUP) && roots[0]) {
    const sourceNode = byId.get(roots[0].id)!;
    const targetNode = byId.get(ROOT_GROUP)!;
    edges.push({ source: sourceNode.id, target: targetNode.id, relation: "contains", sourceNode, targetNode });
  }
  return { width, height, nodes: positioned, edges };
}

export const ROOT_DOCUMENT_GROUP = ROOT_GROUP;
