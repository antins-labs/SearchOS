const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(name) {
  const source = fs.readFileSync(path.join(__dirname, `../src/components/skills/${name}.tsx`), 'utf8');
  const context = { exports: {}, require(name) {
    if (name === '@/lib/api') return {};
    if (name === './SkillUserAction') return load('SkillUserAction');
    return require(name);
  } };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, context);
  return context.exports;
}
const { CreationProgressView: View, AgentRoundsView } = load('SkillCreationProgress');
const job = { id: 'job', status: 'running', stage: 'access_validation', input: { site: 'https://example.com' },
  requests: [{ name: 'example', category: 'access' }], results: [] };
const progress = { job_id: 'job', request_index: 0, phase: 'validate', validation_rounds: 2, execution_count: 5,
  calls: { planner: 3, builder: 4, validator: 6 }, files: ['SKILL.md', 'scripts/run.py'], events: [], regressions: [],
  capabilities: [
    { id: 'search', purpose: '搜索文章与回答', status: 'available', deterministic: 'passed', semantic: 'passed', reason: '来源一致', executions: 3 },
    { id: 'detail', purpose: '保留作者与正文', status: 'unavailable', deterministic: 'passed', semantic: 'failed', reason: '缺少作者', executions: 2 },
    { id: 'answer', purpose: '智答及引用关系', status: 'incomplete', deterministic: 'incomplete', semantic: 'incomplete', reason: '', executions: 0 },
  ] };
const render = (props = {}) => renderToStaticMarkup(React.createElement(View, { job, progress, zh: true, ...props }));

test('展示全部计划能力、执行与内容结论，未完成能力保留分母', () => {
  const html = render();
  for (const text of ['Planner', 'Builder', 'Validator', '正在独立验收', '1 / 3', '2 项待完成', '搜索文章与回答',
    '保留作者与正文', '智答及引用关系', '缺少作者', '执行检查', '内容核验', 'scripts/run.py']) assert.ok(html.includes(text), text);
  assert.match(html, /aria-current="step"/);
  assert.doesNotMatch(html, /全部能力已通过验收/);
});

test('逐轮展示三个角色的模型回复、工具参数与结果', () => {
  const turns = { planner: [{ number: 1, at: null, content: '先研究入口', reasoning: null,
    tool_calls: [{ name: 'search', id: 'a', args: { query: 'science' }, result: { content: '真实结果' } }] }],
  builder: [{ number: 1, at: null, content: '编写脚本', reasoning: '核对字段', tool_calls: [] }], validator: [] };
  const html = renderToStaticMarkup(React.createElement(AgentRoundsView, { zh: true, rounds: { roles: turns } }));
  for (const text of ['Planner', 'Builder', 'Validator', '第 1 轮', '先研究入口', '核对字段',
    '模型回复', 'search', 'science', '真实结果', '暂无轮次记录']) assert.ok(html.includes(text), text);
});

test('修复时显示反馈闭环和原失败输入，停止后使用静态状态', () => {
  const repaired = { ...progress, phase: 'repair', regressions: [{ capability_id: 'detail', reason: '原文章缺少作者' }] };
  const html = render({ progress: repaired });
  for (const text of ['正在根据验收反馈修复', '上次验收说明', '1 个原失败输入待复验', '原文章缺少作者']) assert.ok(html.includes(text), text);
  const stopped = render({ job: { ...job, status: 'interrupted' }, progress: repaired });
  assert.match(stopped, /已停止，进展已保存/);
  assert.doesNotMatch(stopped, /正在根据验收反馈修复|animate-spin|每 3 秒更新/);
});

test('完成任务中的部分通过和完整通过分别展示', () => {
  const complete = { ...job, status: 'completed', stage: 'done' };
  const partial = render({ job: complete, progress: { ...progress, phase: 'complete' } });
  assert.match(partial, /成果已保存，请查看验收结果/);
  assert.doesNotMatch(partial, /全部能力已通过验收/);
  const all = render({ job: complete, progress: { ...progress, phase: 'complete', capabilities: [progress.capabilities[0]] } });
  assert.match(all, /全部能力已通过验收/);
});

test('等待交互时直接显示操作入口，错误与空状态不伪造进度', () => {
  const waiting = render({ job: { ...job, status: 'waiting_user', user_action: {
    id: 'action', state: 'pending', message: '请完成验证', url: 'https://example.com' } } });
  for (const text of ['需要你完成浏览器操作', '请完成验证', '打开浏览器', '已完成，继续']) assert.ok(waiting.includes(text));
  assert.doesNotMatch(waiting, /animate-spin/);
  const empty = render({ job: undefined, progress: null });
  assert.match(empty, /创建过程，一目了然/);
  assert.doesNotMatch(empty, /aria-current|0 \/ 0|全部能力已通过验收/);
  assert.match(render({ progress: null, error: 'HTTP 503' }), /role="alert"/);
});

test('英文界面和多技能请求切换使用对应标签', () => {
  const html = render({ zh: false, job: { ...job, requests: [...job.requests, { name: 'second' }] }, index: 1 });
  for (const text of ['Capability checks', 'Execution', 'Content', 'View findings', 'Validation rounds', 'second']) assert.ok(html.includes(text));
  assert.match(html, /value="1" selected=""/);
});
