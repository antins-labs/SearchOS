/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function load() {
  const source = fs.readFileSync(path.join(__dirname, "../src/lib/localCitations.ts"), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports });
  return exports;
}

async function loadAnswer() {
  const source = fs.readFileSync(path.join(__dirname, "../src/components/conversation/Answer.tsx"), "utf8");
  const markdown = await import("react-markdown");
  const gfm = await import("remark-gfm");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    },
  }).outputText, {
    exports,
    require: (name) => {
      if (name === "react-markdown") return { __esModule: true, ...markdown };
      if (name === "remark-gfm") return { __esModule: true, ...gfm };
      if (name === "@/lib/localCitations") return load();
      return require(name);
    },
  });
  return exports.default;
}

const REF = `local://lib_test/doc_test?rev=${"a".repeat(64)}#W3sicGFnZV9zdGFydCI6Nn1d`;

function loadCellPopover() {
  const source = fs.readFileSync(path.join(__dirname, "../src/components/coverage/CellEvidencePopover.tsx"), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, { exports, document: { body: {} }, require(name) {
    if (name === "react") return { ...require("react"), useRef: (current) => ({ current }) };
    if (name === "react-dom") return { createPortal: (element) => element };
    if (name === "@/hooks/useDialogFocus") return { __esModule: true, default: () => {} };
    if (name === "@/lib/localCitations") return load();
    return require(name);
  } });
  return exports;
}

test("共享事实按当前格的投影显示，不修改任务事实", () => {
  const { evidenceForCell } = loadCellPopover();
  const node = { id: "fact", claim: "Alpha has 120000 residents.", value: "", source: "https://example.org",
    entity: "", attribute: "", status: "active" };
  const ref = { tableId: "b", entity: "Alpha", attribute: "Thousands", cell: {} };
  const result = evidenceForCell([node], ref, [{ evidence_id: "fact", value: "120", alignment: "full", status: "superseded" }]);
  assert.equal(result[0].value, "120");
  assert.equal(result[0].status, "superseded");
  assert.equal(node.value, "");
  assert.equal(node.status, "active");
});

test("表格中的本地证据按钮使用文件名和位置，并打开原文预览", () => {
  const Popover = loadCellPopover().default;
  const node = { id: "fact", claim: "课程安排", entity: "", attribute: "", source: REF, confidence: 0.8,
    local_source_metadata: { file_name: "方案.pdf", locators: [{ kind: "pdf_region", page_start: 7, page_end: 10 }] } };
  let opened;
  const tree = Popover({ nodes: [node], cellRef: { tableId: "t", entity: "A", attribute: "课程", cell: { value: "课程安排", primary_evidence_id: "fact" } },
    bindings: [{ evidence_id: "fact", value: "课程安排", alignment: "full", status: "active" }],
    onClose() {}, onOpenLocalSource(ref) { opened = ref; } });
  function findButton(element) {
    if (!element || typeof element !== "object") return null;
    if (element.type === "button" && element.props.children === "方案.pdf · P7-10") return element;
    for (const child of require("react").Children.toArray(element.props?.children)) {
      const button = findButton(child);
      if (button) return button;
    }
    return null;
  }
  const button = findButton(tree);
  assert.ok(button);
  button.props.onClick();
  assert.equal(opened, REF);
});

test("bare Local sources render as preview buttons in the actual Answer component", async () => {
  const Answer = await loadAnswer();
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: `课程说明。\n\n> 来源：${REF}\n\n后续课程同见 ${REF}。`,
  }));
  assert.equal((html.match(/<button /g) || []).length, 2);
  assert.doesNotMatch(html, /local:\/\//);
  assert.match(html, /查看原文/);
});

test("autolinks and inline handles use short labels while named links keep their labels", async () => {
  const Answer = await loadAnswer();
  const { renderToStaticMarkup } = require("react-dom/server");
  const html = renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: `<${REF}> 和 \`${REF}\`，以及 [课程表](${REF})。`,
  }));
  assert.equal((html.match(/<button /g) || []).length, 3);
  assert.equal((html.match(/查看原文 1/g) || []).length, 2);
  assert.match(html, /课程表<\/button>/);
  assert.doesNotMatch(html, /local:\/\//);
  assert.doesNotMatch(html, /<button[^>]*>[^<]*<button/);
});

test("long web links can wrap without widening the conversation", async () => {
  const Answer = await loadAnswer();
  const { renderToStaticMarkup } = require("react-dom/server");
  const longUrl = `https://example.com/${"unbroken-segment".repeat(80)}`;
  const html = renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: `[${longUrl}](${longUrl})`,
  }));

  assert.match(html, /min-w-0/);
  assert.match(html, /\[overflow-wrap:anywhere\]/);
});

test("table citations preserve punctuation, separate adjacent sources, and leave code examples intact", async () => {
  const Answer = await loadAnswer();
  const { renderToStaticMarkup } = require("react-dom/server");
  const other = REF.replace("doc_test", "doc_other");
  const html = renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: `| 来源 |\n| --- |\n| ${REF},${other}。 |\n\n\`\`\`text\n${REF}\n\`\`\`\n\n[官网](https://example.com)`,
  }));
  assert.equal((html.match(/<button /g) || []).length, 2);
  assert.match(html, /查看原文 1<\/button>,<button/);
  assert.match(html, /查看原文 2<\/button>。/);
  assert.match(html, /<pre><code[^>]*>local:\/\//);
  assert.match(html, /href="https:\/\/example.com"/);
});

test("replayed read observations label bare, named, and native citations with file and location", async () => {
  const { localCitationLabels } = load();
  const native = `local://doc_test/s2?v=${"a".repeat(24)}`;
  const labels = localCitationLabels([{ type: "trajectory", data: {
    type: "local_read_observed", observation: JSON.stringify({
      ref_id: REF, file: "uploads/人工智能-培养方案(1).pdf",
      locators: [{ kind: "pdf_region", page_start: 7, page_end: 10 }],
      tool_content: `[LOCAL_SOURCE]\nSource: ${native}\n\n正文`,
    }),
  } }]);
  assert.equal(labels[REF], "人工智能-培养方案(1).pdf · P7-10");
  assert.equal(labels[native], labels[REF]);
  const Answer = await loadAnswer();
  const html = require("react-dom/server").renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: `来源：${REF}\n\n[原文](${REF})，${native}`,
    localSourceLabels: labels,
  }));
  assert.equal((html.match(/人工智能-培养方案\(1\).pdf · P7-10/g) || []).length, 3);
  assert.equal((html.match(/<button /g) || []).length, 3);
  assert.doesNotMatch(html, /查看原文|uploads\/|local:\/\//);
});

test("source labels support text, slides, and spreadsheets without crossing turn scopes", () => {
  const { localCitationLabels } = load();
  const sources = [
    ["notes.md", { kind: "line_range", start_line: 3, end_line: 8 }, "L3-8"],
    ["slides.pptx", { kind: "slide_object", slide_number: 2 }, "Slide 2"],
    ["data.xlsx", { kind: "cell_range", sheet_name: "课程", range: "A1:D10" }, "课程!A1:D10"],
  ];
  for (const [file, locator, expected] of sources) {
    const labels = localCitationLabels([], [{
      source: REF, local_source_metadata: { file_name: file, locators: [locator] },
    }]);
    assert.equal(labels[REF], `${file} · ${expected}`);
  }
  assert.deepEqual(Object.keys(localCitationLabels([{ type: "trajectory", data: {
    type: "local_read_observed", observation: "{incomplete",
  } }])), []);
  assert.equal(localCitationLabels([])[REF], undefined);
});

test("legacy invalid numbered citations recover from the Evidence Graph", () => {
  const { repairLocalCitationLinks } = load();
  const sources = ["local://library/document?rev=abc#page-1"];
  const markdown = "结论 [资料 1 · P1](invalid-local-reference)。";
  assert.equal(
    repairLocalCitationLinks(markdown, sources),
    `结论 [资料 1 · P1](${sources[0]})。`,
  );
});

test("unresolved invalid links become text instead of opening a dead page", () => {
  const { repairLocalCitationLinks } = load();
  assert.equal(
    repairLocalCitationLinks("结论 [资料 9 · P9](invalid-local-reference)。", []),
    "结论 资料 9 · P9（来源不可用）。",
  );
});

test("unknown fact citations render as unavailable text without a dead link", async () => {
  const Answer = await loadAnswer();
  const html = require("react-dom/server").renderToStaticMarkup(require("react").createElement(Answer, {
    markdown: "结论 [来源](invalid-evidence-reference)。",
  }));
  assert.doesNotMatch(html, /<a /);
  assert.match(html, /来源不可用/);
});

test("Hybrid task evidence renders task relations and filename plus location", () => {
  const source = fs.readFileSync(path.join(__dirname, "../src/components/evidence/EvidenceList.tsx"), "utf8");
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText, { exports, require(name) {
    if (name === "@/lib/localCitations") return load();
    if (name === "@/lib/api") return {
      importNetworkSource: async () => ({}),
      listLocalLibraries: async () => [],
      listNetworkImports: async () => [],
    };
    return require(name);
  } });
  const node = { id: "fact", claim: "需要 120 学分", source: REF, confidence: 0.5,
    entity: "", attribute: "", status: "active", alignment_note: "source_support_verified",
    local_source_metadata: { file_name: "课程.pdf", locators: [{ kind: "pdf_region", page_start: 7, page_end: 10 }] } };
  const html = require("react-dom/server").renderToStaticMarkup(require("react").createElement(exports.default, {
    nodes: [node], defaultView: "tasks", onOpenLocalSource: () => {},
    tasks: [{ id: "read", question: "阅读课程表", status: "completed" },
      { id: "check", question: "联网核实", status: "running" }],
    taskBindings: [{ task_id: "read", evidence_id: "fact", relation: "supports" },
      { task_id: "check", evidence_id: "fact", relation: "context" }],
  }));
  assert.match(html, /阅读课程表/);
  assert.match(html, /联网核实/);
  assert.match(html, /支持/);
  assert.match(html, /背景/);
  assert.match(html, /课程.pdf · P7-10/);
  assert.match(html, /原文支持已核验/);
  assert.doesNotMatch(html, /Quality 30%/);
});

test("Hybrid source limitations remain visible when the execution card is collapsed", () => {
  function moduleAt(relative) {
    const source = fs.readFileSync(path.join(__dirname, "../src", relative), "utf8");
    const exports = {};
    vm.runInNewContext(ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
        jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    }).outputText, { exports, require: (name) => {
      if (name === "@/components/workbench/OrchestratorTimeline") return { __esModule: true, default: () => null };
      if (name.startsWith("@/lib/")) return moduleAt(name.slice(2) + ".ts");
      return require(name);
    } });
    return exports;
  }
  const Card = moduleAt("components/conversation/OrchestrationCard.tsx").default;
  const html = require("react-dom/server").renderToStaticMarkup(require("react").createElement(Card, {
    events: [], workers: [], status: "completed", sourceMode: "hybrid", onOpen: () => {},
    searchState: { source_scope: { mode: "hybrid", documents: [],
      unavailable_sources: { web: "联网来源初始化失败，本轮无法进行外部核实。" } } },
  }));
  assert.match(html, /Hybrid · 运行记录/);
  assert.match(html, /本轮无法进行外部核实/);
  assert.match(html, /aria-expanded="false"/);
  const interrupted = require("react-dom/server").renderToStaticMarkup(require("react").createElement(Card, {
    events: [], workers: [], status: "error", sourceMode: "hybrid", onOpen: () => {},
  }));
  assert.match(interrupted, /Hybrid · 运行未完成/);
  assert.doesNotMatch(interrupted, /bg-ok/);
});

test("历史 evidence 引用解析到本地预览，未知引用不打开新窗口", async () => {
  const Answer = await loadAnswer();
  let opened;
  const tree = Answer({ markdown: "[论文](evidence:fact)", evidenceSources: {fact: REF},
    onOpenLocalSource(ref) { opened = ref; } });
  const href = tree.props.children[0].props.urlTransform("evidence:fact");
  const link = tree.props.children[0].props.components.a({ href, children: "论文" });
  assert.equal(link.type, "button");
  link.props.onClick();
  assert.equal(opened, REF);
  const unknown = tree.props.children[0].props.urlTransform("evidence:missing");
  const unavailable = tree.props.children[0].props.components.a({ href: unknown, children: "未知" });
  assert.equal(unavailable.type, "span");
});

test("References sections retain clickable local sources", async () => {
  const Answer = await loadAnswer();
  const React = require("react");
  const html = require("react-dom/server").renderToStaticMarkup(React.createElement(Answer, {
    markdown: `正文。\n\n## References\n[资料1](${REF})`,
    localSourceLabels: { [REF]: "论文.pdf · P7-10" },
  }));
  assert.match(html, /References/);
  assert.match(html, /论文.pdf · P7-10/);
  assert.match(html, /<button/);
});

test("old answers without inline citations retain an original-file entry", async () => {
  const Answer = await loadAnswer();
  let opened;
  const tree = Answer({ markdown: "论文解读正文，仅有网页链接。",
    localSourceLabels: { [REF]: "论文.pdf · P7-10" }, onOpenLocalSource(ref) { opened = ref; } });
  const section = tree.props.children[1];
  const button = section.props.children[1][0];
  assert.equal(button.props.children, "论文.pdf · P7-10");
  button.props.onClick();
  assert.equal(opened, REF);
});

test("duplicate bracketed web URL opens the original absolute address", async () => {
  const Answer = await loadAnswer();
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const url = "https://visaforkorea-xa.com/customercenter/faq/list/";
  const html = renderToStaticMarkup(React.createElement(Answer, {
    markdown: `韩国旅游签证 [${url}][${url}]。`,
  }));

  assert.match(html, new RegExp(`href="${url}"`));
  assert.doesNotMatch(html, /%5D%5B|\]\[https?:\/\//);
});

test("duplicate bracketed web URL repair leaves code unchanged", () => {
  const { repairMalformedWebLinks } = load();
  const url = "https://example.com/path";
  const malformed = `[${url}][${url}]`;
  const markdown = `${malformed}\n\n\`${malformed}\`\n\n\`\`\`text\n${malformed}\n\`\`\``;

  assert.equal(
    repairMalformedWebLinks(markdown),
    `[${url}](<${url}>)\n\n\`${malformed}\`\n\n\`\`\`text\n${malformed}\n\`\`\``,
  );
});

test("web URL repair preserves valid inline and reference links", () => {
  const { repairMalformedWebLinks } = load();
  const url = "https://example.com/path_(final)?a=1&b=2";
  const markdown = `[官网](${url}) [${url}](<${url}>) [${url}][source]\n\n[source]: ${url}`;

  assert.equal(repairMalformedWebLinks(markdown), markdown);
});

test("single and adjacent bracketed web URLs become independent links", async () => {
  const Answer = await loadAnswer();
  const React = require("react");
  const { renderToStaticMarkup } = require("react-dom/server");
  const first = "https://visaforkorea-xa.com/customercenter/faq/list/";
  const second = "https://pages.trip.com/tour/visa/580.JPG";
  const html = renderToStaticMarkup(React.createElement(Answer, {
    markdown: `单个 [${first}]。相邻 [${first}][${second}]。`,
  }));

  assert.equal((html.match(new RegExp(`href="${first}"`, "g")) || []).length, 2);
  assert.match(html, new RegExp(`href="${second}"`));
  assert.doesNotMatch(html, /\[<a |<\/a>\]|%5D%5B/);
});

test("历史事实引用可展开多个原文链接，内部地址不可点击", async () => {
  const Answer = await loadAnswer();
  const render = require("react-dom/server").renderToStaticMarkup;
  const element = require("react").createElement;
  const html = render(element(Answer, {
    markdown: "结论 [依据](evidence:fact) [缺失](evidence:missing)",
    evidenceSources: { fact: ["https://example.org/v1/a", "https://example.org/v1/b"],
      missing: "agent://worker/summary" },
  }));
  assert.match(html, /href="https:\/\/example.org\/v1\/a"/);
  assert.match(html, /href="https:\/\/example.org\/v1\/b"/);
  assert.doesNotMatch(html, /href="agent:/);
  assert.match(html, /来源不可用/);
});
