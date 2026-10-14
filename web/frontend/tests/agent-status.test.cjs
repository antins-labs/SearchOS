/* eslint-disable @typescript-eslint/no-require-imports */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const cache = new Map();
function load(name) {
  const filename = path.resolve(__dirname, '../src', name);
  if (cache.has(filename)) return cache.get(filename);
  const exports = {};
  cache.set(filename, exports);
  const source = fs.readFileSync(filename, 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  }}).outputText, { exports, require(dep) {
    if (dep.endsWith('ToolCallDetailDialog')) return { __esModule: true, default: () => null };
    if (dep.startsWith('.') || dep.startsWith('@/')) {
      const base = dep.startsWith('@/') ? dep.slice(2) : path.relative(path.join(__dirname,'../src'), path.resolve(path.dirname(filename),dep));
      const file = ['.ts','.tsx'].map(ext => base+ext).find(f => fs.existsSync(path.join(__dirname,'../src',f)));
      return load(file);
    }
    return require(dep);
  }});
  return exports;
}
const event = (data) => ({ type: 'trajectory', data });

test('失败卡片显示真实原因和重新排队状态，工具失败不冒充代理失败', () => {
  const Card = load('components/workbench/AgentCard.tsx').default;
  const { agentIssue } = load('components/workbench/trace.tsx');
  const events = [event({type:'agent_error',agent:'search_agent',error_type:'BadRequestError',error:'LLM is trying to invoke a non-exist tool: "open"'}),
    event({type:'harness',kind:'task_recycled',agent:'search_agent',outcome:'requeued'})];
  const result = renderToStaticMarkup(React.createElement(Card,{data:{name:'search_agent',status:'error',events},onClick(){}}));
  assert.match(result,/模型调用了未注册的工具：open/);
  assert.match(result,/该任务已重新排队/);
  assert.equal(agentIssue([event({type:'tool_call_failed',error:'bad request'})]),null);
  const timeout = agentIssue([event({type:'agent_error',error:'TimeoutError',traceback:'coordinator.py finalize'})]);
  assert.equal(timeout.summary,'证据收尾超时');
  const deferred = agentIssue([event({type:'harness',kind:'evidence_comparison_deferred'})]);
  assert.equal(deferred.summary,'证据已保存，核验已延后');
});

test('子代理输出最终文本后仍等待证据收尾，再以完成事件结束', () => {
  const { foldWorkers } = load('lib/derive.ts');
  const events = [event({type:'dispatch',agent:'search_agent'}),event({type:'agent_final',agent:'search_agent',reasoning:'已找到资料'})];
  assert.equal(foldWorkers(events)[0].status,'running');
  assert.equal(foldWorkers([...events,event({type:'agent_complete',agent:'search_agent'})])[0].status,'completed');
  assert.equal(foldWorkers([...events,event({type:'agent_error',agent:'search_agent',error:'TimeoutError'})])[0].status,'error');
});

test('单次工具报错不会把整个代理标为失败', () => {
  const { foldWorkers } = load('lib/derive.ts');
  const events = [event({type:'dispatch',agent:'search_agent'}), event({type:'step',agent:'search_agent',status:'error'})];
  assert.equal(foldWorkers(events)[0].status,'running');
});
