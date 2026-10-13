/* eslint-disable @typescript-eslint/no-require-imports -- Node 测试使用 CommonJS 加载 TypeScript。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function load(source, dependencies = {}, globals = {}) {
  const code = ts.transpileModule(
    fs.readFileSync(path.join(__dirname, "../src", source), "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } },
  ).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    require(name) {
      assert.ok(name in dependencies, `Unexpected import: ${name}`);
      return dependencies[name];
    },
    ...globals,
  });
  return exports;
}

const derive = load("lib/derive.ts");
const liveUpdates = load("lib/liveUpdates.ts");
const conversation = load("lib/conversation.ts");

test("completed local follow-ups reuse the local conversation session", () => {
  const turns = [{
    id: "t1",
    query: "第一问",
    sessionId: "local-session",
    status: "completed",
    sourceMode: "local",
    events: [],
    workers: [],
    searchState: null,
    answer: "第一答",
    meta: {},
  }];

  assert.equal(
    conversation.continuationSessionId(turns, "local", false),
    "local-session",
  );
  assert.equal(conversation.continuationSessionId(turns, "web", false), "local-session");
  assert.equal(conversation.continuationSessionId(turns, "local", true), undefined);
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function harness() {
  let state;
  let eventHandler;
  let queueUpdates = false;
  const updates = [];
  const polls = [];
  const results = [];
  const intervals = new Map();
  const timeouts = new Map();
  let nextTimeout = 1;
  const react = {
    useState(initial) {
      state = initial;
      return [state, (update) => {
        if (queueUpdates) updates.push(update);
        else state = typeof update === "function" ? update(state) : update;
      }];
    },
    useRef: (current) => ({ current }),
    useCallback: (fn) => fn,
    useEffect: () => {},
  };
  const api = {
    getSearchState() {
      const request = deferred();
      polls.push(request);
      return request.promise;
    },
    getSearchResult() {
      const request = deferred();
      results.push(request);
      return request.promise;
    },
    connectWebSocket(id, onEvent) {
      eventHandler = onEvent;
      return { readyState: 1, close() {} };
    },
  };
  const { useSearch } = load("hooks/useSearch.ts", {
    react, "@/lib/api": api, "@/lib/derive": derive, "@/lib/liveUpdates": liveUpdates,
  }, {
    WebSocket: { CLOSING: 2 },
    setInterval(fn, ms) { intervals.set(ms, fn); return ms; },
    clearInterval(id) { intervals.delete(id); },
    setTimeout(fn) { const id = nextTimeout++; timeouts.set(id, fn); return id; },
    clearTimeout(id) { timeouts.delete(id); },
  });
  return {
    hook: useSearch(), polls, results,
    get state() { return state; },
    poll() { intervals.get(2000)(); },
    complete() { eventHandler({ type: "search_complete" }); },
    event(value) { eventHandler(value); },
    batch() { const pending = [...timeouts.values()]; timeouts.clear(); for (const fn of pending) fn(); },
    intervals,
    queue() { queueUpdates = true; },
    flush() {
      for (const update of updates.splice(0)) {
        state = typeof update === "function" ? update(state) : update;
      }
      queueUpdates = false;
    },
  };
}

const filled = {
  coverage_map: { cells: { "t/a.b": { status: "filled", value: "old" } } },
  evidence_graph: { nodes: [{ id: "e1" }] },
};
const cleared = {
  coverage_map: { cells: { "t/a.b": { status: "missing", value: "" } } },
  evidence_graph: { nodes: [] },
};

async function respond(request, status, search_state) {
  request.resolve({ status, search_state });
  await request.promise;
  await Promise.resolve();
}

test("authoritative snapshots clear cells, remove keys and retract evidence", async () => {
  const h = harness();
  h.hook.attach("s", { searchState: filled });
  await respond(h.polls[0], "running", cleared);
  assert.equal(h.state.liveState, cleared);
  h.poll();
  const empty = { coverage_map: { cells: {} }, evidence_graph: { nodes: [] } };
  await respond(h.polls[1], "running", empty);
  assert.equal(h.state.liveState, empty);
  h.poll();
  await respond(h.polls[2], "running", null);
  assert.equal(h.state.liveState, null);
});

test("an older poll cannot replace a newer reconciliation snapshot", async () => {
  const h = harness();
  h.hook.attach("s");
  h.complete();
  await respond(h.results[0], "running", cleared);
  await respond(h.polls[0], "running", filled);
  assert.equal(h.state.liveState, cleared);
});

test("an older reconciliation cannot replace a newer poll snapshot", async () => {
  const h = harness();
  h.hook.attach("s");
  await respond(h.polls[0], "running", filled);
  h.complete();
  h.poll();
  await respond(h.polls[1], "running", cleared);
  await respond(h.results[0], "running", filled);
  assert.equal(h.state.liveState, cleared);
});

test("terminal snapshots take precedence over in-flight polls", async () => {
  const h = harness();
  h.hook.attach("s");
  h.complete();
  await respond(h.results[0], "completed", cleared);
  await respond(h.polls[0], "running", filled);
  assert.equal(h.state.status, "completed");
  assert.equal(h.state.liveState, cleared);
});

test("a reattached generation ignores old responses even for the same session", async () => {
  const h = harness();
  h.hook.attach("s");
  h.hook.attach("s", { searchState: cleared });
  await respond(h.polls[0], "running", filled);
  assert.equal(h.state.liveState, cleared);
});

test("queued state updates cannot overwrite a terminal snapshot", async () => {
  const h = harness();
  h.hook.attach("s");
  h.complete();
  h.queue();
  await respond(h.polls[0], "running", filled);
  await respond(h.results[0], "completed", cleared);
  h.flush();
  assert.equal(h.state.status, "completed");
  assert.equal(h.state.liveState, cleared);
});

test("worker replay and live updates agree without mutating prior workers", () => {
  const events = [
    { type: "trajectory", data: { agent: "orchestrator", type: "step" } },
    { type: "trajectory", data: { agent: "warmup_1", type: "step" } },
    { type: "blackboard.updated", data: { worker: "search_1", status: "partial" } },
    { type: "trajectory", data: { agent_name: "writer_1", type: "agent_final" } },
    { type: "trajectory", data: { agent: "search_1", type: "agent_error" } },
  ];
  const live = events.reduce(derive.updateWorkers, []);
  const replay = derive.foldWorkers(events);
  assert.equal(JSON.stringify(live), JSON.stringify(replay));
  assert.deepEqual(Array.from(replay, ({ name, intent, status }) => ({ name, intent, status })), [
    { name: "warmup_1", intent: "explore", status: "running" },
    { name: "search_1", intent: "search", status: "error" },
    { name: "writer_1", intent: "write", status: "completed" },
  ]);
  const before = JSON.stringify(live);
  const final = derive.finalizeWorkers(live);
  assert.equal(final[0].status, "completed");
  assert.equal(final[1].status, "error");
  assert.equal(JSON.stringify(live), before);
  Object.freeze(live[0].events);
  Object.freeze(live[0]);
  Object.freeze(live);
  const next = { type: "trajectory", data: { agent: "warmup_1", type: "step" } };
  const first = derive.updateWorkers(live, next);
  const repeated = derive.updateWorkers(live, next);
  assert.equal(first[0].events.length, 2);
  assert.equal(JSON.stringify(first), JSON.stringify(repeated));
});

test("local run progress uses document and evidence semantics", () => {
  const events = [
    { type: "trajectory", data: { type: "task_start", agent: "local_qa", source_mode: "local", document_count: 2 } },
    { type: "evidence_added", node: { id: "e1" } },
    { type: "trajectory", data: { type: "task_complete", agent: "local_qa", source_mode: "local", evidence_count: 3 } },
  ];
  assert.deepEqual(
    JSON.parse(JSON.stringify(derive.deriveLocalRunProgress(events))),
    { present: true, phase: "completed", documentCount: 2, evidenceCount: 3, readCount: 0, citationCount: 0 },
  );
  const workers = derive.foldWorkers(events);
  assert.equal(workers.length, 1);
  assert.equal(workers[0].name, "local_qa");
  assert.equal(workers[0].status, "completed");
});

test("answer stream events expose partial answer before task completion", () => {
  const events = [
    { type: "trajectory", data: { type: "answer_stream_start", phase: "final_answer", stream_id: "final-1" } },
    { type: "trajectory", data: { type: "answer_stream_delta", phase: "final_answer", stream_id: "final-1", delta: "第一段" } },
    { type: "trajectory", data: { type: "answer_stream_delta", phase: "final_answer", stream_id: "final-1", delta: "回答" } },
  ];

  assert.equal(derive.deriveLiveAnswer(events), "第一段回答");
});

test("local reading progress counts observations separately from grounded evidence", () => {
  const events = [
    { type: "trajectory", data: { type: "task_start", source_mode: "local", document_count: 4 } },
    { type: "trajectory", data: { type: "step", source_mode: "local", read_count: 3 } },
  ];
  assert.deepEqual(
    JSON.parse(JSON.stringify(derive.deriveLocalRunProgress(events))),
    { present: true, phase: "answering", documentCount: 4, evidenceCount: 0, readCount: 3, citationCount: 0 },
  );
  events.push({ type: "trajectory", data: {
    type: "task_complete", source_mode: "local", read_count: 5, citation_count: 2, evidence_count: 0,
  } });
  const complete = derive.deriveLocalRunProgress(events);
  assert.equal(complete.phase, "completed");
  assert.equal(complete.readCount, 5);
  assert.equal(complete.citationCount, 2);
  assert.equal(complete.evidenceCount, 0);
});

test("live answer ignores uncommitted model and tool output", () => {
  const intermediateOnly = [
    { type: "trajectory", data: { type: "answer_stream_start", stream_id: "draft-1" } },
    { type: "trajectory", data: { type: "answer_stream_delta", stream_id: "draft-1", delta: "[Local source matches] Metadata" } },
  ];
  assert.equal(derive.deriveLiveAnswer(intermediateOnly), null);

  const events = [
    ...intermediateOnly,
    { type: "trajectory", data: { type: "answer_stream_start", phase: "final_answer", stream_id: "final-2" } },
    { type: "trajectory", data: { type: "answer_stream_delta", phase: "final_answer", stream_id: "final-2", delta: "最终答案" } },
  ];

  assert.equal(derive.deriveLiveAnswer(events), "最终答案");
});

test("a new empty stream clears the previous invocation immediately", () => {
  assert.equal(derive.deriveLiveAnswer([]), null);
  assert.equal(derive.deriveLiveAnswer([
    { type: "trajectory", data: { type: "answer_stream_start", phase: "final_answer", stream_id: "final-2" } },
  ]), "");
});

test("Hybrid mode switches preserve conversation identity", () => {
  const turns = [{ sessionId: "hybrid", status: "completed", sourceMode: "hybrid" }];
  assert.equal(conversation.continuationSessionId(turns, "hybrid", false), "hybrid");
  assert.equal(conversation.continuationSessionId(turns, "web", false), "hybrid");
  assert.equal(conversation.continuationSessionId(turns, "local", false), "hybrid");
});

test("新增表格维度只标记新单元格，保留原值和证据", () => {
  const { diffCoverageMaps } = load("lib/coverageDiff.ts");
  const before = {
    tables: { programmes: { table_id: "programmes", entities: ["Alpha"], attributes: ["Name", "Credits"] } },
    cells: { "programmes/Alpha.Credits": { status: "filled", value: "120", supporting_evidence_ids: ["credits"] } },
  };
  const after = {
    tables: { programmes: { ...before.tables.programmes, attributes: ["Name", "Credits", "Duration.Years"] } },
    cells: { ...before.cells, "programmes/Alpha.Duration.Years": { status: "missing", value: "", supporting_evidence_ids: [] } },
  };
  const changes = diffCoverageMaps(before, after);
  assert.equal(changes.length, 1);
  assert.equal(changes[0].kind, "added");
  assert.equal(changes[0].entity, "Alpha");
  assert.equal(changes[0].attribute, "Duration.Years");
  assert.equal(changes[0].after.status, "missing");
  assert.equal(after.cells["programmes/Alpha.Credits"].supporting_evidence_ids[0], "credits");
});

test("incomplete history is an interrupted run, never a completed answer", () => {
  const interrupted = conversation.restoredRunState("incomplete");
  assert.equal(interrupted.status, "error");
  assert.match(interrupted.error, /中断/);
  assert.match(interrupted.error, /最终回答/);
  assert.equal(conversation.restoredRunState("running").status, "running");
  assert.equal(conversation.restoredRunState("completed").error, null);
  const workers = derive.foldWorkers([
    {type:"trajectory",data:{type:"agent_start",agent:"pdf"}},
    {type:"trajectory",data:{type:"agent_start",agent:"ppt"}},
    {type:"trajectory",data:{type:"agent_complete",agent:"ppt"}},
  ], true, "error");
  assert.equal(workers.find(w => w.name === "pdf").status, "error");
  assert.equal(workers.find(w => w.name === "ppt").status, "completed");
});

test("local budget and timeout completions remain visibly limited", () => {
  for (const reason of ["budget", "timeout"]) {
    const events = [{ type: "trajectory", data: {
      type: "task_complete", source_mode: "local", read_count: 12,
      citation_count: 3, reading_stop_reason: reason,
    } }];
    assert.equal(derive.deriveLocalRunProgress(events).phase, "limited");
    events.push({ type: "trajectory", data: {
      type: "task_complete", source_mode: "local", reading_stop_reason: "answered",
    } });
    assert.equal(derive.deriveLocalRunProgress(events).phase, "completed");
  }
});

test("local execution card labels a budget-limited answer", () => {
  const React = require("react");
  const Card = load("components/conversation/OrchestrationCard.tsx", {
    react: React,
    "react/jsx-runtime": require("react/jsx-runtime"),
    "lucide-react": require("lucide-react"),
    "@/lib/derive": derive, "@/lib/liveUpdates": liveUpdates,
    "@/lib/exploreProgress": { deriveExploreProgress: () => ({ present: false }) },
    "@/components/workbench/OrchestratorTimeline": { default: () => null },
  }).default;
  const html = require("react-dom/server").renderToStaticMarkup(React.createElement(Card, {
    events: [{ type: "trajectory", data: {
      type: "task_complete", source_mode: "local", reading_stop_reason: "budget", read_count: 12,
    } }],
    searchState: null, status: "completed", workers: [], sourceMode: "local", onOpen: () => {},
  }));
  assert.match(html, /已基于已读内容回答 · 阅读受限/);
  assert.doesNotMatch(html, /本地资料回答已生成/);
});

test("versioned deltas preserve old snapshots, untouched branches and removals", () => {
  const initial = { coverage_map: { cells: { a: { value: "old" }, b: { value: "remove" } } }, evidence_graph: { nodes: [{ id: "e1" }] }, frontier: { tasks: [] } };
  const updated = liveUpdates.applyStateChanges(initial, [
    { op: "set", path: ["coverage_map", "cells", "a", "value"], value: "" },
    { op: "delete", path: ["coverage_map", "cells", "b"] },
    { op: "append", path: ["evidence_graph", "nodes"], value: [{ id: "e2" }] },
  ]);
  assert.equal(initial.coverage_map.cells.a.value, "old");
  assert.ok(initial.coverage_map.cells.b);
  assert.equal(updated.coverage_map.cells.a.value, "");
  assert.equal(updated.coverage_map.cells.b, undefined);
  assert.equal(updated.evidence_graph.nodes.length, 2);
  assert.equal(initial.evidence_graph.nodes.length, 1);
  assert.equal(updated.frontier, initial.frontier);
  const cleared = liveUpdates.applyStateChanges(updated, [{ op: "set", path: ["evidence_graph", "nodes"], value: [] }]);
  assert.equal(cleared.evidence_graph.nodes.length, 0);
});

test("event bursts flush once, replay IDs deduplicate, and answers advance incrementally", () => {
  const h = harness();
  h.hook.attach("s");
  assert.equal(h.intervals.has(500), false, "no whole-session render timer");
  h.event({ type: "trajectory", event_id: "trajectory:1", data: { type: "answer_stream_start", phase: "final_answer", stream_id: "final" } });
  for (let i = 0; i < 100; i++) {
    const event = { type: "trajectory", event_id: `trajectory:${i + 2}`, data: { type: "answer_stream_delta", phase: "final_answer", stream_id: "final", delta: "文" } };
    h.event(event); h.event(event);
  }
  assert.equal(h.state.events.length, 0);
  h.batch();
  assert.equal(h.state.events.length, 101);
  assert.equal(h.state.liveAnswer, "文".repeat(100));
});

test("terminal REST status flushes queued events before clearing runtime", async () => {
  const h = harness();
  h.hook.attach("s");
  h.event({ type: "trajectory", event_id: "trajectory:1", data: { type: "step" } });
  await respond(h.polls[0], "completed", filled);
  await respond(h.results[0], "completed", filled);
  assert.equal(h.state.events.length, 1);
  assert.equal(h.state.status, "completed");
});

test("socket deltas apply to their baseline and cannot regress newer REST versions", async () => {
  const h = harness();
  h.hook.attach("s");
  h.event({ type: "state_snapshot", revision: "1-1-1-1-1", state: filled });
  h.event({ type: "state_delta", base_revision: "1-1-1-1-1", revision: "1-1-2-2-1", changes: [{ op: "set", path: ["evidence_graph", "nodes"], value: [] }] });
  assert.equal(h.state.liveState.evidence_graph.nodes.length, 0);
  assert.equal(h.state.events.length, 0, "snapshots must not become transcript events");
  await respond(h.polls[0], "running", filled);
  assert.equal(h.state.liveState.evidence_graph.nodes.length, 0, "in-flight older REST cannot undo socket state");
});
