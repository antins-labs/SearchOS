/* eslint-disable @typescript-eslint/no-require-imports -- 使用真实页面和回调验证重试请求。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const plain = (value) => JSON.parse(JSON.stringify(value));
const sources = (mode = "hybrid", selection = "documents", ids = ["original-doc"]) => ({
  mode, local: { library_id: "original-library", selection, document_ids: ids, model_access: true },
});

function find(node, predicate) {
  if (!node || typeof node !== "object") return undefined;
  if (predicate(node)) return node;
  for (const child of [node.props?.children ?? node].flat()) {
    if (child === node) continue;
    const match = find(child, predicate);
    if (match) return match;
  }
}

function harness() {
  const states = new Map();
  let owner;
  let cursor;
  const react = {
    useState(initial) {
      const slots = states.get(owner);
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === "function" ? initial() : initial;
      return [slots[index], (update) => {
        slots[index] = typeof update === "function" ? update(slots[index]) : update;
      }];
    },
    useRef: (current) => react.useState(() => ({ current }))[0],
    useCallback: (fn) => fn,
    useMemo: (fn) => fn(),
    useEffect: () => {},
  };
  const render = (component, props = {}) => {
    owner = component;
    cursor = 0;
    if (!states.has(owner)) states.set(owner, []);
    return component(props);
  };
  const requests = [];
  let history;
  const localLibrary = {
    selection: sources(),
    restoreSelection(value) { localLibrary.selection = value; },
  };
  const dependencies = {
    react,
    "react/jsx-runtime": { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    "lucide-react": {},
    "@/hooks/useSearch": { useSearch: () => ({
      session: { status: "idle", events: [], workers: [] },
      run: (request) => requests.push(plain(request)), reset() {},
    }) },
    "@/hooks/useLocalLibrary": { useLocalLibrary: () => localLibrary },
    "@/hooks/useLiveFollowUps": { useLiveFollowUps: () => ({ delivered: [], hasSnapshot: false }) },
    "@/lib/api": { loadHistory: async () => history, listHistory: async () => [] },
    "@/lib/activityPreferences": { useActivityPreferences: () => ({ width: 360, tab: "activity" }) },
    "@/components/settings/SettingsProvider": { useSettings: () => ({ overrides: {}, notify() {} }) },
    "./Answer": { default: "Answer", cleanAnswer: (answer) => answer },
  };
  function load(file) {
    const output = {};
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, "../src", file), "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
    }).outputText, {
      exports: output, structuredClone,
      require(name) {
        if (name in dependencies) return dependencies[name];
        if (name.startsWith("@/lib/")) return load(`${name.slice(2)}.ts`);
        if (name.startsWith("@/components/") || name.startsWith("./")) return { default: name.split("/").pop() };
        throw new Error(`Unexpected import: ${name}`);
      },
    });
    return output;
  }
  const Home = load("app/page.tsx").default;
  const Conversation = load("components/conversation/Conversation.tsx").default;
  const page = () => render(Home);
  const conversation = () => find(page(), (node) => node.type === "Conversation").props;
  return {
    requests, localLibrary, conversation,
    submit(selection) {
      find(page(), (node) => node.type === "Landing").props.onSubmit("总结所选文献", { sources: selection });
    },
    async restore(turns) {
      history = { session_id: "saved", status: "error", answer: "", events: [], turns };
      find(page(), (node) => node.type === "HistoryRail").props.onSelect("saved");
      await new Promise(setImmediate);
    },
    retry(index = 0) {
      const props = conversation();
      const tree = render(Conversation, props);
      const view = find(tree, (node) => node.props?.turn === props.turns[index]);
      const turnTree = render(view.type, view.props);
      const button = find(turnTree, (node) => node.type === "button" && node.props.children === "重新运行");
      const actions = find(turnTree, (node) => node.type === "AnswerActions");
      if (button) button.props.onClick();
      else actions.props.onRerun();
      return requests.at(-1);
    },
  };
}

test("提交后立即失败的重试保留文档快照，不使用后来更改的选择", () => {
  const h = harness();
  const original = sources();
  h.submit(original);
  const turn = h.conversation().turns[0];
  turn.status = "error";
  turn.error = "请求失败";
  original.local.document_ids.push("later-doc");
  h.localLibrary.selection = sources("local", "documents", ["other-doc"]);
  const request = h.retry();
  assert.deepEqual(request.sources, sources());
  assert.equal(request.follow_up_to, undefined);
  assert.equal(request.history, undefined);
  assert.deepEqual(plain(h.localLibrary.selection), sources());
});

test("历史失败重试保留显式文档 ID，包括暂时不可用的文档", async () => {
  const h = harness();
  await h.restore([{ query: "历史问题", answer: "", search_state: { source_scope: {
    mode: "hybrid", library_id: "original-library", selection: "documents",
    document_ids: ["original-doc", "unavailable-doc"], documents: [{ document_id: "original-doc" }],
  } } }]);
  assert.deepEqual(h.retry().sources, sources("hybrid", "documents", ["original-doc", "unavailable-doc"]));
});

for (const mode of ["local", "hybrid"]) {
  test(`${mode} 历史整库范围不会缩成当前快照中的文档或丢失空库`, async () => {
    for (const documents of [[], [{ document_id: "original-doc" }]]) {
      const h = harness();
      await h.restore([{ query: "检索整库", answer: "", search_state: { source_scope: {
        mode, library_id: "original-library", selection: "library", document_ids: [], documents,
      } } }]);
      const expected = sources(mode, "library", []);
      assert.deepEqual(plain(h.localLibrary.selection), expected);
      assert.deepEqual(h.retry().sources, expected);
    }
  });
}

test("重跑历史中的旧回答使用该轮文档，兼容只有 documents 的旧快照", async () => {
  const h = harness();
  await h.restore([
    { query: "旧问题", answer: "旧回答", search_state: { source_scope: {
      mode: "local", library_id: "original-library", documents: [{ document_id: "original-doc" }],
    } } },
    { query: "新问题", answer: "", search_state: { source_scope: { mode: "web", documents: [] } } },
  ]);
  const request = h.retry(0);
  assert.equal(request.query, "旧问题");
  assert.deepEqual(request.sources, sources("local"));
  assert.equal(request.follow_up_to, undefined);
});

for (const mode of ["web", "hybrid"]) {
  test(`${mode} 原本未附带本地库的请求重试后仍不附带`, () => {
    const h = harness();
    h.submit({ mode });
    Object.assign(h.conversation().turns[0], { status: "error", error: "失败" });
    assert.deepEqual(h.retry().sources, { mode });
  });
}
