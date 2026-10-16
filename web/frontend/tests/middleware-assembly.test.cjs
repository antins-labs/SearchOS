/* eslint-disable @typescript-eslint/no-require-imports -- Node 加载纯 TypeScript 逻辑。 */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const source = readFileSync(join(__dirname, '../src/lib/middleware-assembly.ts'), 'utf8');
const compiled = { exports: {} };
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText, compiled);
const { insertMiddleware, buildCallChain, previewMounts, assemblyOrderError } = compiled.exports;
const plain = (value) => JSON.parse(JSON.stringify(value));
const item = (id, hooks, requirements = {}) => ({ id, hooks, requirements });

test('拖拽插入支持首尾、向前向后移动、空组合，不重复或修改原数组', () => {
  const original = ['A', 'B', 'C'];
  assert.deepEqual(plain(insertMiddleware(original, 'C', 0)), ['C', 'A', 'B']);
  assert.deepEqual(plain(insertMiddleware(original, 'A', 3)), ['B', 'C', 'A']);
  assert.deepEqual(plain(insertMiddleware(original, 'B', 1)), original);
  assert.deepEqual(plain(insertMiddleware(original, 'B', 2)), original);
  assert.deepEqual(plain(insertMiddleware(original, 'D', 1)), ['A', 'D', 'B', 'C']);
  assert.deepEqual(plain(insertMiddleware([], 'D', 0)), ['D']);
  assert.deepEqual(original, ['A', 'B', 'C']);
});

test('模型调用正确分离 before、wrapper 嵌套、返回和 after', () => {
  const all = ['before_model', 'wrap_model_call', 'after_model'];
  const steps = buildCallChain([item('A', all), item('T', ['wrap_tool_call']), item('B', all)], 'model');
  assert.deepEqual(plain(steps.map(({ id, hook, phase }) => [id ?? 'model', hook, phase])), [
    ['A', 'before_model', 'before'], ['B', 'before_model', 'before'],
    ['A', 'wrap_model_call', 'enter'], ['B', 'wrap_model_call', 'enter'],
    ['model', 'model', 'call'],
    ['B', 'wrap_model_call', 'return'], ['A', 'wrap_model_call', 'return'],
    ['B', 'after_model', 'after'], ['A', 'after_model', 'after'],
  ]);
});

test('工具调用不混入模型钩子；生命周期前向进入、逆向结束', () => {
  const items = [item('A', ['before_agent', 'wrap_tool_call', 'after_agent']),
    item('M', ['wrap_model_call']), item('B', ['before_agent', 'wrap_tool_call', 'after_agent'])];
  assert.deepEqual(plain(buildCallChain(items, 'tool').map((step) => step.id ?? step.hook)), ['A', 'B', 'tool', 'B', 'A']);
  assert.deepEqual(plain(buildCallChain(items, 'agent').map((step) => step.id ?? step.hook)), ['A', 'B', 'agent_loop', 'B', 'A']);
  assert.deepEqual(plain(buildCallChain([], 'model')), [{ hook: 'model', phase: 'call' }]);
});

test('演示条件正确处理互斥与多条件组件，不改变选中配置', () => {
  const items = [item('Always', []), item('EvidenceProgress', [], { extraction_model: true }),
    item('ToolProgress', [], { extraction_model: false }), item('Summary', [], { extraction_model: true, final_summary: true })];
  assert.deepEqual(plain(previewMounts(items, { extraction_model: true, final_summary: false }).map((x) => x.id)), ['Always', 'EvidenceProgress']);
  assert.deepEqual(plain(previewMounts(items, { extraction_model: false, final_summary: true }).map((x) => x.id)), ['Always', 'ToolProgress']);
  assert.equal(items.length, 4);
});

test('禁止把预算记录放到上下文压缩之后', () => {
  assert.equal(assemblyOrderError(['CompactionContextMiddleware', 'BudgetMiddleware']), true);
  assert.equal(assemblyOrderError(['BudgetMiddleware', 'CompactionContextMiddleware']), false);
  assert.equal(assemblyOrderError(['CompactionContextMiddleware']), false);
});
