/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadGraphLayout() {
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/knowledgeGraph.ts"), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports });
  return exports;
}

test("知识库图按主题分组，并保留跨主题边", () => {
  const { layoutKnowledgeGraph } = loadGraphLayout();
  const graph = {
    library_id: "lib_1",
    name: "测试资料",
    nodes: [
      { id: "index:lib_1", node_type: "index", label: "测试资料", summary: "" },
      { id: "subindex:a", node_type: "subindex", label: "主题 A", summary: "" },
      { id: "subindex:b", node_type: "subindex", label: "主题 B", summary: "" },
      { id: "document:1", node_type: "document", label: "共享文档", summary: "" },
    ],
    edges: [
      { source: "index:lib_1", target: "subindex:a", relation: "contains" },
      { source: "index:lib_1", target: "subindex:b", relation: "contains" },
      { source: "subindex:a", target: "document:1", relation: "classifies" },
      { source: "subindex:b", target: "document:1", relation: "classifies" },
    ],
  };
  const layout = layoutKnowledgeGraph(graph, { openedGroupIds: new Set(["subindex:a", "subindex:b"]) });
  const positions = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));

  const root = positions["index:lib_1"];
  const topic = positions["subindex:a"];
  const document = positions["document:1"];
  assert.ok(Number.isFinite(root.x) && Number.isFinite(topic.y) && !document.hidden);
  const onlySecondOpen = layoutKnowledgeGraph(graph, { openedGroupIds: new Set(["subindex:b"]) });
  assert.equal(onlySecondOpen.nodes.find((node) => node.id === "document:1").hidden, false);
  assert.equal(onlySecondOpen.edges.filter((edge) => edge.target === "document:1").length, 2);
  assert.equal(layout.edges.length, 4);
  assert.equal(layout.edges.filter((edge) => edge.target === "document:1").length, 2);
});

test("同一主题文档较多时自动叠放，并可按主题展开", () => {
  const { layoutKnowledgeGraph } = loadGraphLayout();
  const documents = Array.from({ length: 5 }, (_, index) => ({
    id: `document:${index}`,
    node_type: "document",
    label: `文档 ${index}`,
    summary: "",
  }));
  const graph = {
    library_id: "lib_1",
    name: "测试资料",
    nodes: [
      { id: "index:lib_1", node_type: "index", label: "测试资料", summary: "" },
      { id: "subindex:a", node_type: "subindex", label: "主题 A", summary: "" },
      ...documents,
    ],
    edges: [
      { source: "index:lib_1", target: "subindex:a", relation: "contains" },
      ...documents.map((document) => ({ source: "subindex:a", target: document.id, relation: "classifies" })),
    ],
  };

  const initial = layoutKnowledgeGraph(graph);
  assert.equal(initial.nodes.filter((node) => node.node_type === "document" && !node.hidden).length, 0);
  const stacked = layoutKnowledgeGraph(graph, { openedGroupIds: new Set(["subindex:a"]) });
  assert.equal(stacked.nodes.filter((node) => node.node_type === "document" && !node.hidden).length, 1);
  assert.equal(stacked.nodes.find((node) => node.stack)?.stack.count, 5);

  const expanded = layoutKnowledgeGraph(graph, { openedGroupIds: new Set(["subindex:a"]), expandedGroupIds: new Set(["subindex:a"]) });
  assert.equal(expanded.nodes.filter((node) => node.node_type === "document" && !node.hidden).length, 5);
});

test("主页面提供常驻知识库入口并渲染图管理面板", () => {
  const rail = fs.readFileSync(path.join(__dirname, "../src/components/shell/HistoryRail.tsx"), "utf8");
  const page = fs.readFileSync(path.join(__dirname, "../src/app/page.tsx"), "utf8");
  const panel = fs.readFileSync(path.join(__dirname, "../src/components/local/KnowledgeBasePanel.tsx"), "utf8");
  const graph = fs.readFileSync(path.join(__dirname, "../src/components/local/KnowledgeGraphView.tsx"), "utf8");
  const list = fs.readFileSync(path.join(__dirname, "../src/components/local/KnowledgeListView.tsx"), "utf8");
  const documentView = fs.readFileSync(path.join(__dirname, "../src/components/local/DocumentIndexView.tsx"), "utf8");

  assert.match(rail, /onOpenKnowledgeBase/);
  assert.match(rail, /知识库/);
  assert.match(page, /<KnowledgeBasePanel/);
  assert.match(panel, /aria-label="知识库列表"/);
  assert.match(panel, /controller\.renameLibrary/);
  assert.match(panel, /indexes\/\{libraryId\}\//);
  assert.match(panel, /<DocumentIndexView/);
  assert.match(panel, /viewMode === "list"/);
  assert.match(panel, /<KnowledgeListView/);
  assert.match(panel, /hasPendingDocuments/);
  assert.match(panel, /controller\.refreshDocuments\(\)/);
  assert.match(panel, /aria-label="Recap 生成进度"/);
  assert.match(panel, /progress\.completed\}\/\{progress\.total\} segments/);
  assert.match(graph, /onMoveDocument/);
  assert.match(graph, /删除这条分类关系/);
  assert.match(graph, /点击展开文档堆/);
  assert.match(list, /知识库索引列表/);
  assert.match(documentView, /scrollIntoView/);
  assert.match(documentView, /加载更多/);
});

test("密集主题展开后节点不重叠，且完整位于画布内", () => {
  const { layoutKnowledgeGraph } = loadGraphLayout();
  const topics = Array.from({ length: 12 }, (_, i) => ({ id: `t${i}`, node_type: "subindex", label: `主题${i}`, summary: "" }));
  const documents = Array.from({ length: 120 }, (_, i) => ({ id: `d${i}`, node_type: "document", label: `文档${i}`, summary: "" }));
  const graph = {
    nodes: [{ id: "root", node_type: "index", label: "总索引", summary: "" }, ...topics, ...documents],
    edges: documents.map((node, i) => ({ source: topics[i % topics.length].id, target: node.id, relation: "classifies" })),
  };
  const layout = layoutKnowledgeGraph(graph, { openedGroupIds: new Set(topics.map((n) => n.id)), expandedGroupIds: new Set(topics.map((n) => n.id)) });
  const visible = layout.nodes.filter((node) => !node.hidden);
  assert.equal(visible.length, graph.nodes.length);
  assert.equal(layout.edges.length, documents.length);
  for (let i = 0; i < visible.length; i++) {
    const node = visible[i];
    assert.ok(node.x - node.width / 2 >= 0 && node.x + node.width / 2 <= layout.width);
    assert.ok(node.y - node.height / 2 >= 0 && node.y + node.height / 2 <= layout.height);
    for (const other of visible.slice(i + 1)) {
      assert.ok(Math.abs(node.x - other.x) >= (node.width + other.width) / 2 || Math.abs(node.y - other.y) >= (node.height + other.height) / 2, `${node.id} 与 ${other.id} 重叠`);
    }
  }
});


test("展开成员从同一堆叠坐标出发，收起后恢复，布局不拉成长条", () => {
  const { layoutKnowledgeGraph } = loadGraphLayout();
  const docs = Array.from({ length: 12 }, (_, i) => ({ id: `d${i}`, node_type: "document", label: `文档${i}`, summary: "" }));
  const graph = { nodes: [{ id: "root", node_type: "index", label: "库", summary: "" }, { id: "topic", node_type: "subindex", label: "主题", summary: "" }, ...docs], edges: docs.map((doc) => ({ source: "topic", target: doc.id, relation: "classifies" })) };
  const options = { openedGroupIds: new Set(["topic"]) };
  const folded = layoutKnowledgeGraph(graph, options);
  const stack = folded.nodes.find((node) => node.stack);
  assert.ok(folded.nodes.filter((node) => !node.stack && node.node_type === "document").every((node) => node.hidden && node.x === stack.x && node.y === stack.y));
  const expanded = layoutKnowledgeGraph(graph, { ...options, expandedGroupIds: new Set(["topic"]) });
  assert.ok(expanded.height / expanded.width < 2);
  assert.deepEqual(layoutKnowledgeGraph(graph, options), folded);
  assert.deepEqual(new Set(expanded.nodes.map((node) => node.id)), new Set(folded.nodes.map((node) => node.id)));
});

test("初始主题环绕中心分布，逐层展开不将图谱变成树形行列", () => {
  const { layoutKnowledgeGraph } = loadGraphLayout();
  const topics = Array.from({ length: 6 }, (_, i) => ({ id: `t${i}`, node_type: "subindex", label: `主题${i}` }));
  const graph = { nodes: [{ id: "root", node_type: "index", label: "库" }, ...topics], edges: topics.map((topic) => ({ source: "root", target: topic.id, relation: "contains" })) };
  const layout = layoutKnowledgeGraph(graph);
  const root = layout.nodes.find((node) => node.id === "root");
  const neighbors = layout.nodes.filter((node) => node.node_type === "subindex");
  assert.ok(neighbors.some((node) => node.x < root.x) && neighbors.some((node) => node.x > root.x));
  assert.ok(neighbors.some((node) => node.y < root.y) && neighbors.some((node) => node.y > root.y));
  assert.ok(layout.width / layout.height < 2);
  assert.equal(layout.edges.length, 6);
});
