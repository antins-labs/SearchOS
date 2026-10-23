/* eslint-disable @typescript-eslint/no-require-imports -- Node 直接加载交互组件。 */
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const plain = (value) => JSON.parse(JSON.stringify(value));

function harness() {
  const catalog = ['A', 'B', 'C'].map((id) => ({ id, label: { zh: id, en: id },
    description: { zh: `组件 ${id}`, en: id }, category: 'context', hooks: ['wrap_model_call'],
    condition: id === 'C' ? { zh: '需要模型窗口', en: 'Requires model window' } : null }));
  const view = { catalog, pipelines: ['orchestrator', 'writer'].map((id) => ({ id,
    label: { zh: id, en: id }, available: ['A', 'B', 'C'], selected: ['A', 'B'], defaults: ['A', 'B'], customized: false })) };
  const context = { settings: { middleware: view }, status: 'ready', uiPrefs: { language: 'zh' }, notify() {}, fail: false,
    async mutate(args) {
      if (this.fail) return null;
      const result = await args.call();
      this.settings = args.merge(this.settings, result);
      return result;
    } };
  // Provider exposes a bound function in the actual component.
  context.mutate = context.mutate.bind(context);
  const states = [];
  const calls = [];
  let cursor = 0;
  const exports = {};
  const source = readFileSync(join(__dirname, '../src/components/settings/sections/MiddlewareSection.tsx'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, { exports, require(name) {
    if (name === 'react') return { ...React, useId: () => 'middleware-test',
      useState(initial) { const i = cursor++; if (!(i in states)) states[i] = initial;
        return [states[i], (v) => { states[i] = typeof v === 'function' ? v(states[i]) : v; }]; },
      useRef(initial) { const i = cursor++; if (!(i in states)) states[i] = { current: initial }; return states[i]; },
    };
    if (name === '@/components/settings/SettingsProvider') return { useSettings: () => context };
    if (name === '@/components/settings/controls/Toggle') return { __esModule: true, default: 'test-toggle' };
    if (name === '@/components/ui/Select') return { __esModule: true, default: 'test-select' };
    if (name === './MiddlewareWorkbench') return { __esModule: true, default: 'test-workbench' };
    if (name === '@/lib/middleware-assembly') {
      const compiled = { exports: {} };
      vm.runInNewContext(ts.transpileModule(readFileSync(join(__dirname, '../src/lib/middleware-assembly.ts'), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      }).outputText, compiled);
      return compiled.exports;
    }
    if (name === '@/components/settings/primitives') return { SectionShell: 'section', OfflineSkeleton: 'skeleton' };
    if (name === '@/lib/api') return { async putMiddleware(id, selected) {
      calls.push({ id, selected: plain(selected) });
      const result = plain(context.settings.middleware);
      const pipeline = result.pipelines.find((p) => p.id === id);
      pipeline.selected = selected === null ? pipeline.defaults : plain(selected);
      pipeline.customized = selected !== null;
      return result;
    } };
    return require(name);
  } });
  return { calls, context, render() { cursor = 0; return exports.default(); } };
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  for (const child of React.Children.toArray(node.props?.children)) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}
const button = (tree, text) => find(tree, (node) => node.type === 'button' && React.Children.toArray(node.props.children).filter((child) => typeof child === 'string').join('').trim() === text);
const label = (tree, text) => find(tree, (node) => (node.props?.['aria-label'] ?? node.props?.label) === text);

test('勾选与排序先保留草稿，保存后提交真实顺序', async () => {
  const h = harness();
  label(h.render(), '挂载 C').props.onChange();
  label(h.render(), '上移 C').props.onClick();
  assert.equal(h.calls.length, 0);
  await button(h.render(), '保存装配').props.onClick();
  assert.deepEqual(h.calls, [{ id: 'orchestrator', selected: ['A', 'C', 'B'] }]);
  assert.equal(button(h.render(), '保存装配').props.disabled, true);
});

test('切换用途保留各自草稿，失败保留编辑供重试', async () => {
  const h = harness();
  label(h.render(), '挂载 A').props.onChange();
  button(h.render(), 'writer').props.onClick();
  assert.equal(label(h.render(), '挂载 A').props.checked, true);
  button(h.render(), 'orchestrator ·').props.onClick();
  assert.equal(label(h.render(), '挂载 A').props.checked, false);
  h.context.fail = true;
  await button(h.render(), '保存装配').props.onClick();
  assert.equal(label(h.render(), '挂载 A').props.checked, false);
  assert.equal(button(h.render(), '保存装配').props.disabled, false);
  h.context.fail = false;
  await button(h.render(), '保存装配').props.onClick();
  assert.deepEqual(h.calls[0].selected, ['B']);
});

test('空列表可保存，恢复默认发送 null，撤销不发送请求', async () => {
  const h = harness();
  label(h.render(), '挂载 A').props.onChange();
  label(h.render(), '挂载 B').props.onChange();
  await button(h.render(), '保存装配').props.onClick();
  assert.deepEqual(h.calls[0].selected, []);
  await button(h.render(), '恢复默认').props.onClick();
  assert.equal(h.calls[1].selected, null);
  assert.equal(label(h.render(), '挂载 A').props.checked, true);
  label(h.render(), '挂载 C').props.onChange();
  button(h.render(), '撤销修改').props.onClick();
  assert.equal(label(h.render(), '挂载 C').props.checked, false);
  assert.equal(h.calls.length, 2);
});

test('搜索不改变装配，断线禁用写入，旧后端显示升级提示', () => {
  const h = harness();
  label(h.render(), '搜索 Middleware').props.onChange({ target: { value: 'C' } });
  assert.equal(label(h.render(), '挂载 A'), null);
  assert.equal(label(h.render(), '挂载 C').props.checked, false);
  assert.equal(h.calls.length, 0);
  h.context.status = 'offline';
  assert.equal(label(h.render(), '挂载 C').props.disabled, true);
  delete h.context.settings.middleware;
  assert.ok(find(h.render(), (node) => node.type === 'p' && node.props.children.includes('重启 API')));
});

test('可视化与列表共用草稿，切换用途后保留，保存提交可视化顺序', async () => {
  const h = harness();
  button(h.render(), '可视化').props.onClick();
  const workbench = () => find(h.render(), (node) => node.type === 'test-workbench');
  workbench().props.onChange(['C', 'A']);
  button(h.render(), 'writer').props.onClick();
  assert.deepEqual(plain(workbench().props.selected), ['A', 'B']);
  button(h.render(), 'orchestrator ·').props.onClick();
  assert.deepEqual(plain(workbench().props.selected), ['C', 'A']);
  button(h.render(), '列表').props.onClick();
  assert.equal(label(h.render(), '挂载 C').props.checked, true);
  assert.equal(label(h.render(), '挂载 B').props.checked, false);
  assert.equal(label(h.render(), '上移 C').props.disabled, true);
  assert.equal(h.calls.length, 0);
  await button(h.render(), '保存装配').props.onClick();
  assert.deepEqual(h.calls[0].selected, ['C', 'A']);
});
