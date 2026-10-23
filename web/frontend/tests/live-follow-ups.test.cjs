/* eslint-disable @typescript-eslint/no-require-imports -- 用真实 API 和 hook 复现异步状态提交。 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function load(source, dependencies = {}, globals = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', source), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, require: (name) => dependencies[name], ...globals });
  return exports;
}

function harness(fetch) {
  let cursor = 0;
  const slots = [], updates = [], notifications = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (update) => updates.push(() => {
        slots[index] = typeof update === 'function' ? update(slots[index]) : update;
      })];
    },
    useRef(current) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current };
      return slots[index];
    },
    useCallback: (fn) => fn,
    useMemo: (fn) => fn(),
    useEffect() {},
  };
  const globals = { setTimeout, clearTimeout, AbortController, AbortSignal, Headers, URLSearchParams, process: { env: {} }, fetch };
  const api = load('lib/api.ts', {}, globals);
  const { useLiveFollowUps } = load('hooks/useLiveFollowUps.ts', { react, '@/lib/api': api }, globals);
  const render = () => {
    for (const update of updates.splice(0)) update();
    cursor = 0;
    return useLiveFollowUps('active', 'turn-1', true, (message) => notifications.push(message));
  };
  return { render, notifications };
}

const empty = { revision: 0, messages: [] };
const snapshot = (status = 'queued', revision = 1) => ({ revision, messages: [
  { id: 'm1', text: '查询论文', mode: 'after_tool', status },
] });
const ok = (body) => new Response(JSON.stringify(body));

test('移动端立即引导使用同一追问队列并保留服务端回执', async () => {
  const calls = [];
  const h = harness(async (_url, init) => {
    if (init.method === 'POST') {
      calls.push(JSON.parse(init.body));
      return ok({ status: 'queued', queue: snapshot('delivered', 2) });
    }
    return ok(empty);
  });
  assert.equal(await h.render().enqueue('查询论文', 'immediate'), true);
  assert.deepEqual(calls, [{ message: '查询论文', mode: 'immediate' }]);
  assert.equal(h.render().delivered[0].id, 'm1');
  assert.equal(h.render().pending.length, 0);
});

test('旧 API 成功回执缺少 queue 时，状态提交不能使页面崩溃或诱导重发', async () => {
  let posts = 0;
  const h = harness(async (_url, init) => {
    if (init.method === 'POST') { posts++; return ok({ status: 'queued' }); }
    return ok(empty);
  });
  const accepted = await h.render().enqueue('查询论文');
  const view = h.render();
  assert.equal(accepted, true);
  assert.equal(posts, 1);
  assert.equal(view.pending.length, 0);
  assert.equal(view.working.size, 0);
  assert.match(h.notifications.join('\n'), /已提交.*请勿重复发送/);
});

test('旧 API 没有队列查询接口时，保留草稿并且不提交追问', async () => {
  let posts = 0;
  const h = harness(async (_url, init) => {
    if (init.method === 'POST') { posts++; return ok({ status: 'queued' }); }
    return new Response('{"detail":"Method Not Allowed"}', { status: 405 });
  });
  assert.equal(await h.render().enqueue('查询论文'), false);
  assert.equal(posts, 0);
  assert.equal(h.render().pending.length, 0);
  assert.match(h.notifications.join('\n'), /暂时无法读取补充要求/);
});

test('新版回执保留排队和同消息引导行为', async () => {
  const calls = [];
  const h = harness(async (url, init) => {
    calls.push({ url, method: init.method || 'GET' });
    if (url.endsWith('/promote')) return ok(snapshot('delivered', 2));
    if (init.method === 'POST') return ok({ status: 'queued', message_id: 'm1', mode: 'after_tool', queue: snapshot() });
    return ok(empty);
  });
  assert.equal(await h.render().enqueue('查询论文'), true);
  let view = h.render();
  assert.equal(view.pending[0].id, 'm1');
  assert.equal(await view.guide('m1'), true);
  view = h.render();
  assert.equal(view.pending.length, 0);
  assert.equal(view.delivered[0].id, 'm1');
  assert.equal(calls.filter(c => c.url.endsWith('/steer') && c.method === 'POST').length, 1);
});

test('异常队列响应不会替换现有状态，也不会新增一次提交', async () => {
  let corrupt = false, posts = 0;
  const h = harness(async (_url, init) => {
    if (init.method === 'POST') {
      posts++;
      return ok({ status: 'queued', queue: snapshot() });
    }
    return ok(corrupt ? { revision: 2, messages: [null] } : empty);
  });
  await h.render().enqueue('查询论文');
  assert.equal(h.render().pending.length, 1);
  corrupt = true;
  assert.equal(await h.render().enqueue('不要丢失草稿'), false);
  assert.equal(h.render().pending.length, 1);
  assert.equal(posts, 1);
  assert.match(h.notifications.join('\n'), /暂时无法确认补充要求的状态/);
});
