/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

function loadApi(fetch, globals = {}) {
  const timers = new Map();
  const context = {
    exports: {}, process: { env: {} }, fetch, AbortController, AbortSignal,
    URLSearchParams, Headers,
    setTimeout(fn, delay) { timers.set(fn, delay); return fn; },
    clearTimeout(fn) { timers.delete(fn); },
    ...globals,
  };
  const source = readFileSync(join(__dirname, '../src/lib/api.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, context);
  return { api: context.exports, timers };
}

test('知识库管理正确编码主题 ID，并发送编辑和删除请求', async () => {
  const calls = [];
  const { api } = loadApi(async (url, init) => {
    calls.push({ url, method: init.method, body: init.body && JSON.parse(init.body) });
    return new Response(JSON.stringify({ nodes: [], edges: [] }));
  });
  await api.saveLocalTopic('lib_a', '新主题', '说明');
  await api.saveLocalTopic('lib_a', '改名', '手工说明', '人工智能');
  await api.editLocalDocument('lib_a', 'doc_b', '资料');
  await api.deleteLocalDocument('lib_a', 'doc_b');
  await api.deleteLocalTopic('lib_a', '人工智能');
  await api.deleteLocalLibrary('lib_a');
  assert.deepEqual(calls.map(c => c.method), ['POST', 'PATCH', 'PATCH', 'DELETE', 'DELETE', 'DELETE']);
  assert.ok(calls[1].url.endsWith('/topics/' + encodeURIComponent('人工智能')));
  assert.deepEqual(calls[1].body, { title: '改名', summary: '手工说明' });
  assert.deepEqual(calls[2].body, { name: '资料' });
  assert.ok(calls[5].url.endsWith('/libraries/lib_a'));
});

test('设置保存复用超时请求并保留请求正文', async () => {
  const { api, timers } = loadApi(async (url, init) => {
    assert.equal(url, 'http://localhost:8000/api/settings/effort');
    assert.equal(init.method, 'PUT');
    assert.deepEqual(JSON.parse(init.body), { level: 'high', overrides: {} });
    assert.equal(init.signal.aborted, false);
    assert.deepEqual([...timers.values()], [12000]);
    return new Response('{"level":"high"}');
  });
  assert.equal((await api.putEffort('high')).level, 'high');
  assert.equal(timers.size, 0);
});

test('错误解析支持字符串、数组和嵌套 detail', async () => {
  for (const [detail, expected] of [['denied', 'denied'], [['a', 'b'], 'a; b'], [{ detail: 'nested' }, 'nested']]) {
    const { api, timers } = loadApi(async () => new Response(JSON.stringify({ detail }), { status: 400 }));
    await assert.rejects(api.putEffort('high'), { message: expected });
    assert.equal(timers.size, 0);
  }
});

test('健康和设置读取失败返回 null，预设读取仍抛错', async () => {
  const { api } = loadApi(async () => new Response('invalid json'));
  assert.equal(await api.getHealth(), null);
  assert.equal(await api.getSettings(), null);
  await assert.rejects(api.getProviderPresets());
});

test('无正文操作接受 204', async () => {
  const { api } = loadApi(async () => new Response(null, { status: 204 }));
  assert.equal(await api.stopSearch('s1'), undefined);
  assert.equal(await api.deleteHistory('s1'), undefined);
});

test('保存来源页面携带会话页面标识，而不是证据内容', async () => {
  const { api } = loadApi(async (url, init) => {
    assert.equal(url, 'http://localhost:8000/api/local/libraries/lib-a/imports');
    assert.equal(init.method, 'POST');
    assert.deepEqual(JSON.parse(init.body), {
      source_url: 'https://example.com/report',
      title: '',
      index_after_save: true,
      session_id: 'session-a',
      page_id: 'abc123',
    });
    return new Response(JSON.stringify({ job_id: 'import-a' }));
  });

  await api.importNetworkSource('lib-a', 'https://example.com/report', {
    indexAfterSave: true,
    sessionId: 'session-a',
    pageId: 'abc123',
  });
});

test('repair 保留 35 秒预算和缺失路由提示', async () => {
  const { api, timers } = loadApi(async () => {
    assert.deepEqual([...timers.values()], [35000]);
    return new Response('{"detail":"Not Found"}', { status: 404 });
  });
  await assert.rejects(api.startRepair('s1', {}), /Repair API unavailable/);
  assert.equal(timers.size, 0);
});

test('诊断预算覆盖响应正文读取，超时会取消请求', async () => {
  let signal;
  let readingBody;
  const bodyReady = new Promise((resolve) => { readingBody = resolve; });
  const { api, timers } = loadApi(async (_url, init) => {
    signal = init.signal;
    return {
      ok: true,
      json: () => new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
        readingBody();
      }),
    };
  });
  const pending = api.testProvider('synthesis');
  await bodyReady;
  assert.deepEqual([...timers.values()], [65000]);
  for (const timer of timers.keys()) timer();
  await assert.rejects(pending, /Request timed out/);
  assert.equal(signal.aborted, true);
  assert.equal(timers.size, 0);
});

test('本地文件上传区分传输进度与服务端解析阶段', async () => {
  class FakeFormData {
    append(name, file, filename) { this.entry = { name, file, filename }; }
  }
  class FakeXMLHttpRequest {
    static latest;
    constructor() { this.upload = {}; FakeXMLHttpRequest.latest = this; }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(name, value) { this.headers = { ...this.headers, [name]: value }; }
    send(body) {
      this.body = body;
      this.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 });
      this.upload.onload();
      this.status = 200;
      this.responseText = JSON.stringify({ document_id: 'doc_1', searchable: true });
      this.onload();
    }
  }
  const { api } = loadApi(async () => { throw new Error('fetch should not be used'); }, {
    FormData: FakeFormData,
    XMLHttpRequest: FakeXMLHttpRequest,
  });
  const phases = [];
  const file = { name: 'notes.pdf', size: 10 };
  const document = await api.uploadLocalDocument('lib 1', file, (progress) => phases.push(progress));

  assert.equal(FakeXMLHttpRequest.latest.method, 'POST');
  assert.equal(FakeXMLHttpRequest.latest.url, 'http://localhost:8000/api/local/libraries/lib%201/uploads');
  assert.equal(FakeXMLHttpRequest.latest.timeout, 180000);
  assert.equal(FakeXMLHttpRequest.latest.withCredentials, true);
  assert.equal(FakeXMLHttpRequest.latest.headers["X-SearchOS-Request"], "1");
  assert.deepEqual(Array.from(phases, (item) => [item.phase, item.percent]), [
    ['uploading', 50],
    ['parsing', 100],
  ]);
  assert.equal(document.document_id, 'doc_1');
});

test('本地 PDF 原件链接保留已校验页码', () => {
  const { api } = loadApi(async () => { throw new Error('fetch should not be used'); });
  const citation = {
    library_id: 'lib 1',
    document_id: 'doc/1',
    locators: [{ kind: 'pdf_region', page_start: 6, page_end: 6 }],
  };
  assert.equal(
    api.localOriginalUrl(citation),
    'http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/original#page=6',
  );
});

test('Office 预览链接使用转换端点并定位幻灯片', () => {
  const { api } = loadApi(async () => { throw new Error('fetch should not be used'); });
  const citation = {
    library_id: 'lib 1',
    document_id: 'doc/1',
    preview_mode: 'office',
    locators: [{ kind: 'slide_object', slide_number: 4 }],
  };
  assert.equal(
    api.localPreviewUrl(citation),
    'http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/preview#page=4',
  );
});

test('本地索引作业取消与重试调用显式端点', async () => {
  const requests = [];
  const { api } = loadApi(async (url, init) => {
    requests.push([url, init.method]);
    return new Response('{"job_id":"job_1","status":"queued"}');
  });
  await api.cancelLocalIndexJob('lib 1', 'job/1');
  await api.retryLocalIndexJob('lib 1', 'job/1');
  assert.deepEqual(requests, [
    ['http://localhost:8000/api/local/libraries/lib%201/index-jobs/job%2F1/cancel', 'POST'],
    ['http://localhost:8000/api/local/libraries/lib%201/index-jobs/job%2F1/retry', 'POST'],
  ]);
});

test('知识库图和文档预览使用资料库边界内的端点', async () => {
  const requests = [];
  const { api } = loadApi(async (url) => {
    requests.push(url);
    return new Response('{"library_id":"lib 1","name":"资料","nodes":[],"edges":[]}');
  });
  await api.getLocalLibraryGraph('lib 1');
  assert.deepEqual(requests, [
    'http://localhost:8000/api/local/libraries/lib%201/graph',
  ]);
  assert.equal(
    api.localDocumentPreviewUrl('lib 1', 'doc/1', 'pptx'),
    'http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/preview',
  );
  assert.equal(
    api.localDocumentPreviewUrl('lib 1', 'doc/1', 'pdf'),
    'http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/original',
  );
});

test('知识库重命名保留稳定 library id 并使用 PATCH', async () => {
  let captured;
  const { api } = loadApi(async (url, init) => {
    captured = [url, init.method, JSON.parse(init.body)];
    return new Response('{"library_id":"lib 1","name":"课程资料","created_at":"now"}');
  });

  const renamed = await api.renameLocalLibrary('lib 1', '课程资料');

  assert.deepEqual(captured, [
    'http://localhost:8000/api/local/libraries/lib%201',
    'PATCH',
    { name: '课程资料' },
  ]);
  assert.equal(renamed.library_id, 'lib 1');
  assert.equal(renamed.name, '课程资料');
});

test('知识库关系编辑和文档索引按边界编码参数', async () => {
  const requests = [];
  const { api } = loadApi(async (url, init = {}) => {
    requests.push([url, init.method || 'GET', init.body ? JSON.parse(init.body) : null]);
    return new Response('{}');
  });

  await api.setLocalDocumentTopics('lib 1', 'doc/1', ['主题 A']);
  await api.getLocalDocumentIndex('lib 1', 'doc/1');
  await api.getLocalDocumentSegment('lib 1', 'doc/1', 'P1#2', 20000);

  assert.deepEqual(requests, [
    ['http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/topics', 'PUT', { subindex_ids: ['主题 A'] }],
    ['http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/index', 'GET', null],
    ['http://localhost:8000/api/local/libraries/lib%201/documents/doc%2F1/segment?segment_id=P1%232&offset=20000', 'GET', null],
  ]);
});

test('技能创建提交意图并通过作业接口读取进度', async () => {
  const calls = [];
  const { api } = loadApi(async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ id: 'job', status: 'queued' }));
  });
  const input = { kind: 'site', site: 'https://example.com', text: '', categories: ['access'], max_requests: 1 };
  assert.equal((await api.createSkills(input)).status, 'queued');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), input);
  await api.getSkillCreation('job/id');
  assert.equal(calls[1].url, 'http://localhost:8000/api/skills/creations/job%2Fid');
  await api.listSkillCreations();
  assert.equal(calls[2].init.cache, 'no-store');
});

test('技能查询携带关键词、分类和分页参数', async () => {
  const { api } = loadApi(async (url) => {
    const parsed = new URL(url);
    assert.equal(parsed.pathname, '/api/skills/library/query');
    assert.equal(parsed.searchParams.get('q'), 'RSS 搜索');
    assert.equal(parsed.searchParams.get('category'), 'access');
    assert.equal(parsed.searchParams.get('page'), '2');
    assert.equal(parsed.searchParams.get('page_size'), '12');
    return new Response(JSON.stringify({ items: [], total: 0, page: 1, pages: 0, page_size: 12, counts: {} }));
  });
  assert.equal((await api.querySkillLibrary({ q: 'RSS 搜索', category: 'access', page: 2, page_size: 12 })).total, 0);
});

test('运行中追问保留投递时机，默认立即引导', async () => {
  const calls = [];
  const { api } = loadApi(async (url, init) => {
    assert.equal(url, 'http://localhost:8000/api/search/active/steer');
    calls.push(JSON.parse(init.body));
    return new Response('{"status":"queued"}');
  });
  await api.steerSearch('active', '查询论文');
  await api.steerSearch('active', '补充来源', 'after_tool');
  assert.deepEqual(calls, [
    { message: '查询论文', mode: 'immediate' },
    { message: '补充来源', mode: 'after_tool' },
  ]);
});

test('待处理追问按消息 ID 提升和删除，返回队列回执', async () => {
  const calls = [];
  const snapshot = { revision: 3, messages: [{ id: 'message/id', text: '论文', mode: 'immediate', status: 'queued' }] };
  const { api } = loadApi(async (url, init) => {
    calls.push({ url, method: init.method || 'GET' });
    return new Response(JSON.stringify(snapshot));
  });
  assert.equal((await api.getSteeringQueue('active')).revision, 3);
  assert.equal((await api.promoteSteeringMessage('active', 'message/id')).messages[0].id, 'message/id');
  assert.equal((await api.removeSteeringMessage('active', 'message/id')).revision, 3);
  assert.deepEqual(calls, [
    { url: 'http://localhost:8000/api/search/active/steer', method: 'GET' },
    { url: 'http://localhost:8000/api/search/active/steer/message%2Fid/promote', method: 'POST' },
    { url: 'http://localhost:8000/api/search/active/steer/message%2Fid', method: 'DELETE' },
  ]);
});

test('队列查询与变更拒绝不完整回执，避免错误数据进入 React 状态', async () => {
  const malformed = [null, {}, { revision: 0 }, { revision: 1, messages: null },
    { revision: 1, messages: [null] }, { revision: -1, messages: [] },
    { revision: 2, messages: [{ id: 'm', text: '论文', mode: 'unknown', status: 'queued' }] }];
  for (const payload of malformed) {
    const { api } = loadApi(async () => new Response(JSON.stringify(payload)));
    await assert.rejects(api.getSteeringQueue('active'), /响应不兼容/);
    await assert.rejects(api.promoteSteeringMessage('active', 'm'), /响应不兼容/);
    await assert.rejects(api.removeSteeringMessage('active', 'm'), /响应不兼容/);
  }
});

test('mobile requests use same origin, cookie credentials and CSRF header', async () => {
  const { api } = loadApi(async (url, init) => {
    assert.equal(url, '/api/search');
    assert.equal(init.credentials, 'include');
    assert.equal(init.headers.get('X-SearchOS-Request'), '1');
    assert.equal(init.headers.get('Content-Type'), 'application/json');
    return new Response('{"session_id":"s"}');
  }, { window: { location: { origin: 'https://search.example.test' } } });
  await api.startSearch({ query: 'test' });
});

test('mobile websocket uses current secure origin', () => {
  let url;
  const { api } = loadApi(() => {}, {
    window: { location: { origin: 'https://search.example.test' } },
    WebSocket: class { constructor(value) { url = value; } },
  });
  api.connectWebSocket('session', () => {});
  assert.equal(url, 'wss://search.example.test/api/ws/session');
});
