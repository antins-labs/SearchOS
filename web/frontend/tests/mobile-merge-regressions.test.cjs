/* eslint-disable @typescript-eslint/no-require-imports -- 执行真实移动组件与回调验证合并边界。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function find(node, predicate) {
  if (!node || typeof node !== "object") return undefined;
  if (predicate(node)) return node;
  for (const child of [node.props?.children ?? node].flat()) {
    if (child === node) continue;
    const match = find(child, predicate);
    if (match) return match;
  }
}

function harness(file, props) {
  const states = [], submitted = [], rerun = [];
  let cursor = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
      return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
    },
    useRef: current => ({ current }),
    useEffect() {},
    useMemo: fn => fn(),
  };
  const dependencies = {
    react,
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "lucide-react": {},
    "@/hooks/useHostStatus": { useHostStatus: () => ({ phase: "online", refresh() {} }) },
    "@/lib/hostStatus": { HOST_LABELS: { online: "主机在线" } },
    "@/lib/mobileSources": { mobileSourceSelection: () => ({ mode: "web" }) },
    "@/lib/coverageTables": { declaredCoverageTables: () => [] },
    "@/lib/mobileReportPreview": { mobileReportExcerpt: () => "摘要" },
    "@/lib/localCitations": { localCitationLabels: () => ({}) },
    "@/components/conversation/Answer": { __esModule: true, default: "Answer", cleanAnswer: value => value },
    "@/components/settings/SettingsProvider": { useSettings: () => ({ overrides: {}, setOverride() {}, notify() {} }) },
    "./AssistantPanels": { useAssistant: () => ({ plans: [], inbox: { unread: 0 }, refresh() {} }) },
  };
  const output = {};
  const source = fs.readFileSync(path.join(__dirname, "../src/components/mobile", file), "utf8");
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  } }).outputText, {
    exports: output,
    URL, Date, setTimeout,
    window: { location: { origin: "https://search.example.org" }, history: { replaceState() {} } },
    require(name) {
      if (name in dependencies) return dependencies[name];
      return { __esModule: true, default: name.endsWith(".module.css")
        ? new Proxy({}, { get: (_, key) => key }) : name.split("/").pop() };
    },
  });
  props = { ...props, onSubmit: (...args) => submitted.push(args), onRerun: turn => rerun.push(turn) };
  const render = () => { cursor = 0; return output.default(props); };
  return { render, submitted, rerun };
}

const turn = () => ({
  id: "turn", sessionId: "original-session", skillGenerationId: "generation-1",
  query: "Original question", answer: "Original answer", status: "completed",
  events: [], workers: [], meta: {}, sources: { mode: "local", local: { document_ids: ["original"] } },
});

const props = original => ({
  turns: [original], history: [], historyStatus: "ready", loadingId: null,
  running: false, stopping: false, localLibrary: {
    mode: "web", documents: [], selectedDocumentIds: [], uploads: [], uploading: false,
  }, onOpen: async () => true,
});

test("移动新建使用当前输入发起 fresh run，不把输入当成旧轮次重跑", () => {
  const h = harness("MobileAssistant.tsx", props(turn()));
  find(h.render(), node => node.props?.["aria-label"] === "交办新任务").props.onClick();
  find(h.render(), node => node.type === "textarea").props.onChange({ target: { value: "A new question" } });
  find(h.render(), node => node.type === "MobileSheet").props.footer.props.onClick();
  assert.equal(h.submitted.length, 1);
  assert.equal(h.submitted[0][0], "A new question");
  assert.deepEqual(JSON.parse(JSON.stringify(h.submitted[0][1])), { sources: { mode: "web" } });
  assert.equal(h.submitted[0][2], true);
  assert.deepEqual(h.rerun, []);
});

test("新版移动会话保留原轮次重跑与技能变化卡片", async () => {
  const original = turn(), h = harness("MobileAssistant.tsx", props(original));
  find(h.render(), node => node.props?.className === "briefCard").props.onClick();
  await new Promise(setImmediate);
  const view = find(h.render(), node => node.type?.name === "MobileTurn");
  view.props.onRerun();
  assert.equal(h.rerun[0], original);
  assert.deepEqual(h.submitted, []);
  const rendered = view.type(view.props);
  const changes = find(rendered, node => node.type === "SkillChanges");
  assert.equal(changes.props.sessionId, "original-session");
  assert.equal(changes.props.generationId, "generation-1");
  assert.ok(find(rendered, node => node.type === "MobileReport"));
});

test("实时与定时报告共用的阅读组件保留同一证据的全部来源", () => {
  const h = harness("MobileReport.tsx", {
    query: "Report", answer: "Answer", inlineReader: true,
    searchState: { evidence_graph: { nodes: [
      { id: "many", source: "https://example.org/first", source_urls: ["https://example.org/first", "https://example.org/second"] },
      { id: "legacy", source: "https://example.org/legacy" },
      { id: "removed", source: "https://example.org/removed", status: "removed" },
    ] } },
  });
  find(h.render(), node => node.props?.className === "readReport").props.onClick();
  const reader = find(h.render(), node => node.type === "Answer");
  assert.deepEqual(JSON.parse(JSON.stringify(reader.props.evidenceSources)), {
    many: ["https://example.org/first", "https://example.org/second"],
    legacy: "https://example.org/legacy",
  });
});
